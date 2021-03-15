import sys, traceback
import asyncio
from aio_pika import connect_robust, Message, DeliveryMode, ExchangeType, IncomingMessage
from aio_pika import exceptions as aio_pika_exception
import yaml
import os


class AMQ_Pub_Sub:
    def __init__(self, eventloop, config_file, pub_sub_name, mode="pub", app_callback=None):
        try:
            if os.path.exists( config_file ):
                with open( config_file, 'r' ) as yaml_file:
                    yaml_as_dict = yaml.load( yaml_file, Loader=yaml.FullLoader )
                    entry = yaml_as_dict["robot_generator"]["amq"]

                    self.broker_info = entry["broker"]
                    self.credential_info = entry["credentials"]
                    self.binding_keys = list()
                    for pub_sub in entry["pub_sub"]:
                        if pub_sub_name == pub_sub["name"]:
                            self.exchange_name = pub_sub["exchange"]
                            for binding in pub_sub["binding_keys"]:
                                self.binding_keys.append( binding )

                    self.eventloop = eventloop
                    self.connection = None
                    self.channel = None
                    self.exchange = None
                    self.app_callback = app_callback
                    self.mode = mode
        except FileNotFoundError as e:
            print( e )
            print( "** Traceback **" )
            exc_type, exc_value, exc_traceback = sys.exc_info()
            print( repr( traceback.format_exception( exc_type, exc_value, exc_traceback ) ) )
            sys.exit()
        except OSError as e:
            print( e )
            print( "** Traceback **" )
            exc_type, exc_value, exc_traceback = sys.exc_info()
            print( repr( traceback.format_exception( exc_type, exc_value, exc_traceback ) ) )
            sys.exit()
        except yaml.YAMLError as e:
            print( e )
            print( "** Traceback **" )
            exc_type, exc_value, exc_traceback = sys.exc_info()
            print( repr( traceback.format_exception( exc_type, exc_value, exc_traceback ) ) )
            sys.exit()
        except:
            print( "unhandled exception" )
            print( "** Traceback **" )
            exc_type, exc_value, exc_traceback = sys.exc_info()
            print( repr( traceback.format_exception( exc_type, exc_value, exc_traceback ) ) )
            sys.exit()

    async def connect(self):
        if self.mode == "pub":
            await self._pub_connect()
        else:
            await self._sub_connect()

    async def _pub_connect(self):
        try:
            self.connection = await connect_robust( login=self.credential_info["username"], password=self.credential_info["password"],
                                                    host=self.broker_info["address"], port=self.broker_info["port"], loop=self.eventloop )
            self.channel = await self.connection.channel()
            self.exchange = await self.channel.declare_exchange( self.exchange_name, ExchangeType.FANOUT )
        except aio_pika_exception.AMQPException as e:
            print( e )
            print( "** Traceback **" )
            exc_type, exc_value, exc_traceback = sys.exc_info()
            print( repr( traceback.format_exception( exc_type, exc_value, exc_traceback ) ) )
            sys.exit()
        except:
            print( "unhandled exception" )
            print( "** Traceback **" )
            exc_type, exc_value, exc_traceback = sys.exc_info()
            print( repr( traceback.format_exception( exc_type, exc_value, exc_traceback ) ) )
            sys.exit()

    async def _sub_connect(self):
        try:
            self.connection = await connect_robust( login=self.credential_info["username"], password=self.credential_info["password"],
                                                    host=self.broker_info["address"], port=self.broker_info["port"], loop=self.eventloop )
            self.channel = await self.connection.channel()
            await self.channel.set_qos( prefetch_count=1 )
            self.exchange = await self.channel.declare_exchange( self.exchange_name, ExchangeType.FANOUT )
            queue = await self.channel.declare_queue( exclusive=True )
            for binding in self.binding_keys:
                await queue.bind( exchange=self.exchange, routing_key=binding)
            await queue.consume( self._sub_on_message )
        except aio_pika_exception.AMQPException as e:
            print( e )
            print( "** Traceback **" )
            exc_type, exc_value, exc_traceback = sys.exc_info()
            print( repr( traceback.format_exception( exc_type, exc_value, exc_traceback ) ) )
            sys.exit()
        except:
            print( "unhandled exception" )
            print( "** Traceback **" )
            exc_type, exc_value, exc_traceback = sys.exc_info()
            print( repr( traceback.format_exception( exc_type, exc_value, exc_traceback ) ) )
            sys.exit()

    async def _sub_on_message(self, message: IncomingMessage):
        async with message.process():
            if self.app_callback is not None:
                self.app_callback(exchange_name=message.exchange, binding_name=message.routing_key, message_body = message.body )

    async def publish(self, binding_key, message_content, priority=0):
        try:
            if binding_key in self.binding_keys:
                message = Message( body=message_content, delivery_mode=DeliveryMode.NOT_PERSISTENT, priority=priority )
                await self.exchange.publish( message, routing_key=binding_key )
            else:
                print("Binding key does not match. Failed to Publish")
        except aio_pika_exception.AMQPException as e:
            print( e )
            print( "** Traceback **" )
            exc_type, exc_value, exc_traceback = sys.exc_info()
            print( repr( traceback.format_exception( exc_type, exc_value, exc_traceback ) ) )
            sys.exit()
        except:
            print( "unhandled exception" )
            print( "** Traceback **" )
            exc_type, exc_value, exc_traceback = sys.exc_info()
            print( repr( traceback.format_exception( exc_type, exc_value, exc_traceback ) ) )
            sys.exit()

    async def terminate(self):
        await self.connection.close()


if __name__ == "__main__":
    def sub_app_callback(**kwargs):
        print( kwargs )


    async def subtest():
        pub = AMQ_Pub_Sub( eventloop=event_loop, config_file="personnel.yaml", pub_sub_name="personnel_1", mode="sub", app_callback=sub_app_callback )
        await pub.connect()

    async def pubtest():
        event_loop = asyncio.get_event_loop()
        pub = AMQ_Pub_Sub( eventloop=event_loop, config_file="personnel.yaml", pub_sub_name="vws_1", mode="pub" )
        event_loop.run_until_complete( pub.connect() )
        while True:
            event_loop.run_until_complete( pub.publish( binding_key="info.1", message_content="test message" ) )
            await asyncio.sleep( 1 )


    event_loop = asyncio.get_event_loop()
    event_loop.run_until_complete(subtest())
    event_loop.run_forever()