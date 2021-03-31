import argparse
import asyncio
import functools
import logging
import os
import signal
import sys

import yaml

from RoboGen.model import RobotArm2

logging.basicConfig(
    level=logging.WARNING,
    format='%(levelname)-8s [%(filename)s:%(lineno)d] %(message)s'
)

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

    for robot in config["robot"]:
        robo = RobotArm2( event_loop=eventloop, robot_info=robot, sequence_conf=config["sequence"], amq_config=config["amq"] )
        await robo.connect()
        robos.append(robo)

    while not sighup_handler_var:
        for robo in robos:
            await robo.update()

    del robo
    sighup_handler_var = False


def main():
    """Initialization"""
    args = parse_arguments()
    if not os.path.isfile(args.config):
        logging.error("configuration file not readable. Check path to configuration file")
        sys.exit()

    if os.path.exists( args.config ):
        with open( args.config, 'r' ) as yaml_file:
            yaml_as_dict = yaml.load( yaml_file, Loader=yaml.FullLoader )

    event_loop = asyncio.get_event_loop()
    event_loop.add_signal_handler(signal.SIGHUP, functools.partial(signal_handler, name='SIGHUP'))
    event_loop.run_until_complete(app(event_loop, yaml_as_dict["robot_generator"]))


if __name__ == "__main__":
    main()
