import argparse
import asyncio
import functools
import logging
import os
import signal
import sys

import yaml

from RoboGen.model import RobotArm2

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger(__name__)

handler = logging.FileHandler('/tmp/robogen.log')
handler.setLevel(logging.ERROR)

formatter = logging.Formatter('%(levelname)-8s-[%(filename)s:%(lineno)d]-%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


sighup_handler_var = False


def parse_arguments():
    """Arguments to run the script"""
    parser = argparse.ArgumentParser(description='Robot motion generator')
    parser.add_argument('--config', '-c', required=True, help='YAML Configuration File for RobotMotionGen with path')
    return parser.parse_args()


def signal_handler(name):
    print(f'signal_handler {name}')
    global sighup_handler_var
    sighup_handler_var = True


async def app(eventloop, config):
    robos = []
    global sighup_handler_var

    while True:
        # Read configuration
        try:
            generator_config = read_config(config)
        except Exception as e:
            logger.error(f'Error while reading configuration: {e}')
            break
        logger.debug("Robot Generator Version: %s", generator_config['version'])
        for robot in generator_config["robots"]:
            robo = RobotArm2(
                event_loop=eventloop,
                robot_info=robot,
                amq_config=generator_config["amq"])
            await robo.connect()
            robos.append(robo)

        while not sighup_handler_var:
            for robo in robos:
                await robo.update()

        # If SIGHUP Occurs, Delete the instances
        for each_robot in robos:
            del each_robot
        sighup_handler_var = False


def read_config(yaml_config_file):
    """Parse the given Configuration File"""
    if os.path.exists(yaml_config_file):
        with open(yaml_config_file, 'r') as config_file:
            yaml_as_dict = yaml.load(config_file, Loader=yaml.FullLoader)
        return yaml_as_dict['robot_generator']
    else:
        raise FileNotFoundError


def main():
    """Initialization"""
    args = parse_arguments()
    if not os.path.isfile(args.config):
        logging.error("configuration file not readable. Check path to configuration file")
        sys.exit(-1)

    event_loop = asyncio.get_event_loop()
    event_loop.add_signal_handler(signal.SIGHUP, functools.partial(signal_handler, name='SIGHUP'))
    event_loop.run_until_complete(app(event_loop, args.config))


if __name__ == "__main__":
    main()
