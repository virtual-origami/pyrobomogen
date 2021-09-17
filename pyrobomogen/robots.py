import asyncio
import json
import logging
import sys
from pyrobomogen.in_mem_db import RedisDB
from pyrobomogen.robot import RobotArm2
from pyrobomogen.pub_sub import PubSubAMQP

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG,
                    format='%(levelname)-8s [%(filename)s:%(lineno)d] %(message)s')
logger = logging.getLogger("Robots:WS")


class WSRobots:
    def __init__(self, eventloop, config):
        self.publishers = []
        self.subscribers = []
        self.robots_in_ws = []
        self.update_interval = config["update_interval"]["sample_interval"]
        self.redis_db = RedisDB(host=config["in_mem_db"]["server"]["address"],
                                port=config["in_mem_db"]["server"]["port"],
                                password=config["in_mem_db"]["credentials"]["password"])

        # check for protocol key
        if "protocol" not in config:
            logger.error("no 'protocol' key found.")
            sys.exit(-1)

        for publisher in config["protocol"]["publishers"]:
            if publisher["type"] == "amq":
                logger.debug('Setting Up AMQP Publisher for Robot')
                self.publishers.append(
                    PubSubAMQP(
                        eventloop=eventloop,
                        config_file=publisher,
                        binding_suffix=""
                    )
                )
            else:
                logger.error("Provide protocol amq config")
                raise AssertionError("Provide protocol amq config")

        for subscribers in config["protocol"]["subscribers"]:
            if subscribers["type"] == "amq":
                logger.debug('Setting Up AMQP Subcriber for Robot')
                self.subscribers.append(
                    PubSubAMQP(
                        eventloop=eventloop,
                        config_file=subscribers,
                        binding_suffix="",
                        app_callback=self.consume_control_msg
                    )
                )
            else:
                logger.error("Provide protocol amq config")
                raise AssertionError("Provide protocol amq config")

        # robot instantiation
        for robot in config["robots"]:
            robo = RobotArm2(event_loop=eventloop, robot_info=robot)
            state_information = {
                "base": robo.base.tolist(),
                "shoulder": robo.shoulder.tolist(),
                "length_shoulder_to_elbow": robo.length_shoulder_to_elbow,
                "length_elbow_to_gripper": robo.length_elbow_to_gripper
            }
            key_name = "robot_" + robo.id
            json_state_information = json.dumps(state_information)
            self.redis_db.set(key=key_name, value=json_state_information)

            # add new instance to robots in workspace list
            self.robots_in_ws.append(robo)

    async def publish(self, exchange_name, msg):
        """publish: publish robotic arm movement data to Message Broker
        - msg: message content
        """
        for publisher in self.publishers:
            if exchange_name == publisher.exchange_name:
                await publisher.publish(message_content=msg)
                logger.debug(f'Pub: Exchange:{exchange_name} Msg:{msg}')

    async def connect(self):
        """connect: connect to the Message Broker
        """
        for publisher in self.publishers:
            await publisher.connect()

        for subscriber in self.subscribers:
            await subscriber.connect(mode="subscriber")

    async def robot_control_msg_handler(self, exchange_name, binding_name, message_body):
        msg_attributes = message_body.keys()
        if ("id" in msg_attributes) and ("control" in msg_attributes):
            for robo in self.robots_in_ws:
                if robo.id == message_body["id"]:
                    logger.debug(f'Sub: Exchange: {exchange_name} Msg:{message_body}')
                    robo.control_msg_handler(message_body=message_body)
                    break

    async def consume_control_msg(self, **kwargs):

        exchange_name = kwargs["exchange_name"]
        binding_name = kwargs["binding_name"]
        message_body = json.loads(kwargs["message_body"])

        # check for matching subscriber with exchange and binding name in all subscribers
        for subscriber in self.subscribers:
            # if subscriber.exchange_name == exchange_name:
            cb_str = subscriber.get_callback_handler_name()
            if cb_str is not None:
                try:
                    cb = getattr(self, cb_str)
                except:
                    logging.critical(f'No Matching handler found for {cb_str}')
                    continue
                if cb is not None:
                    await cb(exchange_name=exchange_name, binding_name=binding_name, message_body=message_body)

    async def update(self):
        for robo in self.robots_in_ws:
            await robo.update()
            if robo.generator_result is not None and robo.visual_result is not None and robo.control == "start":
                await self.publish(
                    exchange_name="generator_robot",
                    msg=json.dumps(robo.generator_result).encode())
                await self.publish(
                    exchange_name="visual",
                    msg=json.dumps(robo.visual_result).encode())

        await asyncio.sleep(self.update_interval)

    def remove(self):
        for each_robot in self.robots_in_ws:
            del each_robot
