"""
AMQP Publish/Subscribe Wrapper Class for Robot Arm

Authors:
    Karthik <she@biba.uni-bremen.de>
    update: initial version of wrapper class
    Shantanoo <des@biba.uni-bremen.de, shantanoo.desai@gmail.com>
    update: Apply linting
"""
import asyncio
import sys
import logging
from aio_pika import connect_robust, Message, DeliveryMode, ExchangeType, IncomingMessage
from aio_pika import exceptions as aio_pika_exception

# logger for this file
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler('/tmp/robogen.log')
handler.setLevel(logging.ERROR)
formatter = logging.Formatter('%(levelname)-8s-[%(filename)s:%(lineno)d]-%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


class AMQ_Pub_Sub:
    def __init__(self, eventloop, config_file, binding_suffix, mode='publisher', app_callback=None):
        try:
            self.broker_info = config_file["broker"]
            self.credential_info = config_file["credential"]
            self.binding_keys = list()
            self.exchange_name = config_file["exchange"]
            self.mode = mode
            for binding in config_file["binding_keys"]:
                self.binding_keys.append(binding)

            self.binding_suffix = binding_suffix
            self.eventloop = eventloop
            self.connection = None
            self.channel = None
            self.exchange = None
            self.app_callback = app_callback

        except Exception as e:
            logger.critical(e)
            sys.exit(-1)

    async def connect(self):
        if self.mode == 'publisher':
            await self._pub_connect()
        elif self.mode == 'subscriber':
            await self._sub_connect()
        else:
            logger.critical('AMQ must be "publisher" or "subscriber"')
            sys.exit(-1)

    async def _pub_connect(self):
        try:
            self.connection = await connect_robust(
                login=self.credential_info["username"],
                password=self.credential_info["password"],
                host=self.broker_info["address"],
                port=self.broker_info["port"],
                loop=self.eventloop
            )
            self.channel = await self.connection.channel()
            self.exchange = await self.channel.declare_exchange(self.exchange_name, ExchangeType.FANOUT)
        except aio_pika_exception.AMQPException as e:
            logger.critical(e)
            sys.exit(-1)
        except Exception as e:
            logger.critical(e)
            sys.exit(-1)

    async def _sub_connect(self):
        try:
            self.connection = await connect_robust(
                login=self.credential_info["username"],
                password=self.credential_info["password"],
                host=self.broker_info["address"],
                port=self.broker_info["port"],
                loop=self.eventloop)
            self.channel = await self.connection.channel()
            await self.channel.set_qos(prefetch_count=1)
            self.exchange = await self.channel.declare_exchange(self.exchange_name,ExchangeType.FANOUT)
            queue = await self.channel.declare_queue(exclusive=True)
            for binding in self.binding_keys:
                await queue.bind(exchange=self.exchange,routing_key=binding + self.binding_suffix)
            await queue.consume(self._sub_on_message)
        except Exception as e:
            logger.critical(e)
            sys.exit(-1)

    async def _sub_on_message(self, message: IncomingMessage):
        async with message.process():
            logger.debug(f"Msg received: Exchange {message.exchange}, Routing {message.routing_key}")
            if self.app_callback is not None:
                self.app_callback(
                    exchange_name=message.exchange,
                    binding_name=message.routing_key,
                    message_body=message.body
                )

    async def publish(self,message_content,priority=0):
        try:
            for binding_key in self.binding_keys:
                message = Message(
                    body=message_content,
                    delivery_mode=DeliveryMode.NOT_PERSISTENT,
                    priority=priority
                )
                logger.debug(f'Msg Publish: Exchange: {self.exchange_name}, Routing:{binding_key + self.binding_suffix}')
                await self.exchange.publish(message,routing_key=binding_key + self.binding_suffix)
        except aio_pika_exception.AMQPException as e:
            logger.critical(e)
            sys.exit(-1)
        except Exception as e:
            logger.critical(e)
            sys.exit(-1)

    async def terminate(self):
        await self.connection.close()