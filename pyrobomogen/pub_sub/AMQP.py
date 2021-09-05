"""
AMQP Publish/Subscribe Wrapper Class for Robot Arm

Authors:
    Karthik <she@biba.uni-bremen.de>
    Shantanoo <des@biba.uni-bremen.de, shantanoo.desai@gmail.com>

ChangeLog:
    - update: initial version of wrapper class
    - update: Apply linting
    - update: Refactor Class with documentation
"""

import sys
import logging
from aio_pika import connect_robust, Message, DeliveryMode, ExchangeType, IncomingMessage
from aio_pika import exceptions as aio_pika_exception

# logger for this file
logger = logging.getLogger("PubSub:AMQP")
logging.basicConfig(stream=sys.stdout,
                    level=logging.DEBUG,
                    format='%(levelname)-2s [%(filename)s:%(lineno)d] %(message)s')
aio_pika_logger = logging.getLogger('aio_pika')
aio_pika_logger.setLevel(logging.ERROR)


class PubSubAMQP:
    def __init__(self, eventloop, config_file, binding_suffix, app_callback=None):
        """PubSubAMQP:
        - eventloop: AsyncIO EventLoop
        - config_file: Python Dictionary with configuration of AMQP Broker
        - binding_suffix: Binding Suffix necessary for Publishing on dedicated routing key
        - mode: Publish/Subscribe (default: 'publisher')
        - app_callback: Callback function  (default: None)
        """
        try:
            self.broker_info = config_file["broker"]
            self.credential_info = config_file["credential"]
            self.binding_keys = list()
            self.exchange_name = config_file["exchange"]
            for binding in config_file["binding_keys"]:
                self.binding_keys.append(binding)

            self.binding_suffix = binding_suffix
            self.eventloop = eventloop
            self.connection = None
            self.channel = None
            self.exchange = None
            self.app_callback = app_callback

            logger.debug('RabbitMQ Exchange: %s', self.exchange_name)
            logger.debug('Binding Suffix: %s', self.binding_suffix)

        except Exception as e:
            logger.error('Error while Creating PubSubAMQP Instance')
            logger.error(e)
            sys.exit(-1)

    async def connect(self, mode="publisher"):
        """connect: Connect to the Message Broker"""
        try:
            logger.debug('Connecting the Broker: amqp://%s %s', self.broker_info["address"], self.broker_info["port"])
            self.connection = await connect_robust(
                login=self.credential_info["username"],
                password=self.credential_info["password"],
                host=self.broker_info["address"],
                port=self.broker_info["port"],
                loop=self.eventloop
            )
            self.channel = await self.connection.channel()
            if mode == "subscriber":
                await self._sub_connect()
        except aio_pika_exception.AMQPException as e:
            logger.error('Exception while Connecting to Broker')
            logger.error(e)
            sys.exit(-1)

    async def _sub_connect(self):
        """_sub_connect: private method for subscribing data to Broker. Setup dedicated channel, exchange"""
        try:
            await self.channel.set_qos(prefetch_count=1)
            self.exchange = await self.channel.declare_exchange(self.exchange_name, ExchangeType.FANOUT)
            queue = await self.channel.declare_queue(exclusive=True)
            for binding in self.binding_keys:
                await queue.bind(exchange=self.exchange, routing_key=binding + self.binding_suffix)
            await queue.consume(self._sub_on_message)
        except Exception as e:
            logger.error('_sub_connect: Exception during setup of sub channel, exchange')
            logger.error(e)
            await self.terminate()
            sys.exit(-1)

    async def _sub_on_message(self, message: IncomingMessage):
        """_sub_on_message: private method to handle consumption of message during subscription"""

        async with message.process():
            # logger.debug(f"msg received: Exchange {message.exchange}, Routing {message.routing_key}")
            if self.app_callback is not None:
                self.app_callback(
                    exchange_name=message.exchange,
                    binding_name=message.routing_key,
                    message_body=message.body
                )

    async def publish(self, message_content, priority=0):
        """publish: Produce Message to Message Broker
        - message_content: payload of message to be published
        - priority: message priority
        """
        try:
            self.exchange = await self.channel.declare_exchange(self.exchange_name, ExchangeType.FANOUT)
            for binding_key in self.binding_keys:
                message = Message(
                    body=message_content,
                    delivery_mode=DeliveryMode.NOT_PERSISTENT,
                    priority=priority
                )
                # logger.debug(
                #     f'msg Publish: Exchange: {self.exchange_name}, Routing:{binding_key + self.binding_suffix}'
                # )
                await self.exchange.publish(message, routing_key=binding_key + self.binding_suffix)
        except aio_pika_exception.AMQPException as e:
            logger.error(e)
            await self.terminate()
            sys.exit(-1)
        except Exception as e:
            logger.error('Exception during Publishing Message to Broker')
            logger.error(e)
            await self.terminate()
            sys.exit(-1)

    async def terminate(self):
        """terminate: close the connection to the broker"""
        await self.connection.close()
