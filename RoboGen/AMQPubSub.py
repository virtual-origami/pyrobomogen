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

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger(__name__)

pika_logger = logging.getLogger('aio_pika')
pika_logger.setLevel(logging.WARNING)

handler = logging.FileHandler('/tmp/robogen.log')
handler.setLevel(logging.ERROR)

formatter = logging.Formatter('%(levelname)-8s-[%(filename)s:%(lineno)d]-%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


class AMQ_Pub_Sub:
    def __init__(self, eventloop, config_file, binding_suffix, app_callback=None):
        try:
            self.broker_info = config_file["broker"]
            self.credential_info = config_file["credential"]
            self.binding_keys = list()
            self.exchange_name = config_file["exchange"]
            for binding in config_file["binding_keys"]:
                self.binding_keys.append(binding)

            self.eventloop = eventloop
            self.connection = None
            self.channel = None
            self.exchange = None
            self.app_callback = app_callback
            self.binding_suffix = binding_suffix
        except Exception as e:
            logger.critical(e)
            sys.exit(-1)

    async def connect(self):
        # FEATURE FOR LATER: Subscription if necessary
        await self._pub_connect()

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
            self.exchange = await self.channel.declare_exchange(self.exchange_name, ExchangeType.FANOUT)
            queue = await self.channel.declare_queue(exclusive=True)
            for binding in self.binding_keys:
                await queue.bind(exchange=self.exchange, routing_key=binding)
            await queue.consume(self._sub_on_message)
        except aio_pika_exception.AMQPException as e:
            logger.critical(e)
            sys.exit(-1)
        except Exception as e:
            logger.critical(e)
            sys.exit(-1)

    async def _sub_on_message(self, message: IncomingMessage):
        async with message.process():
            if self.app_callback is not None:
                self.app_callback(
                    exchange_name=message.exchange,
                    binding_name=message.routing_key+self.binding_suffix,
                    message_body=message.body
                )

    async def publish(self, binding_key, message_content, priority=0):
        try:
            if binding_key in self.binding_keys:
                message = Message(
                    body=message_content,
                    delivery_mode=DeliveryMode.NOT_PERSISTENT,
                    priority=priority
                )
                await self.exchange.publish(message, routing_key=binding_key+self.binding_suffix)
            else:
                logger.critical("Binding key does not match. Failed to Publish")
        except aio_pika_exception.AMQPException as e:
            logger.critical(e)
            sys.exit(-1)
        except Exception as e:
            logger.critical(e)
            sys.exit(-1)

    async def terminate(self):
        await self.connection.close()


# EXAMPLE
if __name__ == "__main__":

    def sub_app_callback(**kwargs):
        logger.debug(kwargs)

    async def subtest():
        pub = AMQ_Pub_Sub(
            eventloop=event_loop,
            config_file="robot.yaml",
            pub_sub_name="robot_1",
            app_callback=sub_app_callback
        )
        await pub.connect()

    async def pubtest():
        event_loop = asyncio.get_event_loop()
        pub = AMQ_Pub_Sub(
            eventloop=event_loop,
            config_file="robot.yaml",
            pub_sub_name="robot_1"
        )
        await pub.connect()
        while True:
            await pub.publish(binding_key="telemetry", message_content="test message".encode())
            await asyncio.sleep(1)

    if (len(sys.argv) > 1) and (sys.argv[1] == "sub"):
        # subscriber test
        event_loop = asyncio.get_event_loop()
        event_loop.run_until_complete(subtest())
        event_loop.run_forever()
    elif (len(sys.argv) > 1) and (sys.argv[1] == "pub"):
        # publisher test
        event_loop = asyncio.get_event_loop()
        event_loop.run_until_complete(pubtest())
    else:
        print("in valid command line argument, "
              "\n publisher format: python filename.py pub"
              "\n subscriber format: python filename.py sub")

    event_loop = asyncio.get_event_loop()
    event_loop.run_until_complete(subtest())
    event_loop.run_forever()
