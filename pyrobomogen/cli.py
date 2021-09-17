"""Command-Line Utility Python Script to be installed as binary
   usage: robot-generator -c /path/to/config.yaml
"""

import argparse
import asyncio
import functools
import logging
import os
import signal
import sys
import yaml
from pyrobomogen.robots import WSRobots

logging.basicConfig(level=logging.DEBUG, format='%(levelname)-8s [%(filename)s:%(lineno)d] %(message)s')

# logger for this file
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler('/tmp/robogen.log')
handler.setLevel(logging.ERROR)
formatter = logging.Formatter('%(levelname)-8s-[%(filename)s:%(lineno)d]-%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# TURN OFF asyncio logger
asyncio_logger = logging.getLogger('asyncio')
asyncio_logger.setLevel(logging.WARNING)

wdt_logger = logging.getLogger('watchdog_timer')
wdt_logger.setLevel(logging.WARNING)

is_sighup_received = False
ws_robots = None


def _graceful_shutdown():
    global ws_robots
    if ws_robots is not None:
        ws_robots.remove()


def parse_arguments():
    """Arguments to run the script"""
    parser = argparse.ArgumentParser(description='Robotic Arm Motion Generator')
    parser.add_argument('--config', '-c', required=True, help='YAML Configuration File for RobotMotionGen with path')
    return parser.parse_args()


def sighup_handler(name):
    """SIGHUP HANDLER"""
    # logger.debug(f'signal_handler {name}')
    logger.info('Updating the Robotic Configuration')
    global is_sighup_received
    is_sighup_received = True


async def app(eventloop, config):
    """Main application for Robot Generator"""
    global ws_robots
    global is_sighup_received

    while True:
        # Read configuration
        try:
            generator_config = read_config(config)
        except Exception as e:
            logger.error('Error while reading configuration:')
            logger.error(e)
            break

        logger.debug("Robot Generator Version: %s", generator_config['version'])

        ws_robots = WSRobots(eventloop=eventloop, config=generator_config)
        await ws_robots.connect()

        # continuously monitor signal handle and update robot motion
        while not is_sighup_received:
            await ws_robots.update()
        # If SIGHUP Occurs, Delete the instances
        _graceful_shutdown()

        # reset sighup handler flag
        is_sighup_received = False


def read_config(yaml_config_file):
    """Parse the given Configuration File"""
    if os.path.exists(yaml_config_file):
        with open(yaml_config_file, 'r') as config_file:
            yaml_as_dict = yaml.load(config_file, Loader=yaml.FullLoader)
        return yaml_as_dict['robot_generator']
    else:
        logger.error('YAML Configuration File not Found.')
        raise FileNotFoundError


def app_main():
    """Initialization"""
    args = parse_arguments()
    if not os.path.isfile(args.config):
        logging.error("configuration file not readable. Check path to configuration file")
        sys.exit(-1)

    event_loop = asyncio.get_event_loop()
    event_loop.add_signal_handler(signal.SIGHUP, functools.partial(sighup_handler, name='SIGHUP'))
    try:
        event_loop.run_until_complete(app(event_loop, args.config))
    except KeyboardInterrupt:
        logger.error('CTRL+C Pressed')
        _graceful_shutdown()
