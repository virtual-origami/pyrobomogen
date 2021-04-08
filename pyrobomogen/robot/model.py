# The MIT License (MIT)

# Copyright (c) 2016 - 2021 Atsushi Sakai

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""
Original Code Snippet used from:
https://github.com/AtsushiSakai/PythonRobotics/blob/master/ArmNavigation/two_joint_arm_to_point_control/two_joint_arm_to_point_control.py

Inverse kinematics of a two-joint arm
Left-click the plot to set the goal position of the end effector

Authors: Daniel Ingram (daniel-s-ingram)
         Atsushi Sakai (@Atsushi_twi)
         Karthik <she@biba.uni-bremen.de>
         Shantanoo <des@biba.uni-bremen.de, shantanoo.desai@gmail.com>

Ref: [P. I. Corke, "Robotics, Vision & Control",
    Springer 2017, ISBN 978-3-319-54413-7 p102](https://link.springer.com/book/10.1007/978-3-642-20144-8)


Changelog:
    - update-1:Dec-06-2020 :Converted the Original function implementation to class based implementation
    - update-2:Mar-03-2021 :Apply Linting on File, remove unused imports and variables
    - update-3:Apr-04-2021 :Refactor Code usage to include `pub_sub` module + Documentation + add MIT License

"""
import asyncio
import json
import logging
import math
import sys

import numpy as np

from pyrobomogen.pub_sub.AMQP import PubSubAMQP

# logger for this file
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG,
                    format='%(levelname)-8s [%(filename)s:%(lineno)d] %(message)s')
logger = logging.getLogger("Robot:Model")


class RobotArm2:
    """This class implements Robot Arm with 2 joint ARM
    """

    def __init__(self, event_loop, robot_info):
        """RobotArm2: Two-Joint Robotic Arm Model
        - event_loop: Python AsyncIO Eventloop
        - robot_info: Python Dictionary with configuration of the Robot
        """
        try:
            if robot_info is None:
                logger.error("Robot Information Cannot Be None")
                sys.exit(-1)

            self.id = robot_info["id"]
            self.proportional_gain = robot_info["motion"]["control"]["proportional_gain"]
            self.sample_time = robot_info["motion"]["control"]["sample_rate"]
            self.length_shoulder_to_elbow = robot_info["arm"]["length"]["shoulder_to_elbow"]
            self.length_elbow_to_gripper = robot_info["arm"]["length"]["elbow_to_gripper"]
            self.base = np.array(
                [robot_info["initial_position"]["base"]["x"], robot_info["initial_position"]["base"]["y"]]
            )
            self.shoulder = np.array(
                [robot_info["initial_position"]["base"]["x"], robot_info["initial_position"]["base"]["y"]]
            )
            self.motion_pattern = robot_info["motion"]["pattern"]["task_coordinates"]

            self.theta1 = 0.0
            self.theta2 = 0.0
            self.GOAL_THRESHOLD = 0.01

            self.destination_coordinate = [0, 0]
            self.previous_destination_coordinate = self.destination_coordinate

            self.sequence_count = 0

            self.eventloop = event_loop
            self.publishers = []
            self.subscribers = []
            self.control = robot_info["motion"]["operation_state"]

            logger.debug(
                f'Initial Values: Theta1={self.theta1}, Theta2={self.theta2}, GOAL_THRESHOLD={self.GOAL_THRESHOLD}')
            logger.debug(
                f'Initial Values: Previous Destination Coordinates Set to: {self.previous_destination_coordinate}')
            for publisher in robot_info["protocol"]["publishers"]:
                if publisher["type"] == "amq":
                    logger.debug('Setting Up AMQP Publisher for Robot')
                    self.publishers.append(
                        PubSubAMQP(
                            eventloop=self.eventloop,
                            config_file=publisher,
                            binding_suffix=self.id
                        )
                    )
                else:
                    logger.error("Provide protocol amq config")
                    raise AssertionError("Provide protocol amq config")

            for subscribers in robot_info["protocol"]["subscribers"]:
                if subscribers["type"] == "amq":
                    logger.debug('Setting Up AMQP Subcriber for Robot')
                    self.subscribers.append(
                        PubSubAMQP(
                            eventloop=self.eventloop,
                            config_file=subscribers,
                            binding_suffix=self.id,
                            app_callback=self.consume_control_msg
                        )
                    )
                else:
                    logger.error("Provide protocol amq config")
                    raise AssertionError("Provide protocol amq config")

        except Exception as e:
            logger.error("Exception during creation of RobotArm2", e)
            sys.exit(-1)

    async def publish(self, exchange_name, msg):
        """publish: publish robotic arm movement data to Message Broker
        - msg: message content
        """
        for publisher in self.publishers:
            if exchange_name == publisher.exchange_name:
                await publisher.publish(message_content=msg)
                logger.debug(msg)

    async def connect(self):
        """connect: connect to the Message Broker
        """
        for publisher in self.publishers:
            await publisher.connect()

        for subscriber in self.subscribers:
            await subscriber.connect(mode="subscriber")

    def update_operation_state(self, state):
        if state == "start":
            self.control = "start"
        elif state == " stop":
            self.control = "stop"
        else:
            logger.error("Invalid operational state received")

    async def update(self):
        """update: Computes the inverse kinematics for a planar 2DOF arm.
        When out of bounds, rewrite x and y with last correct values
        """
        try:
            if self.control == "start":
                if math.sqrt(
                        (self.destination_coordinate[0] ** 2) +
                        (self.destination_coordinate[1] ** 2)
                ) > (
                        self.length_shoulder_to_elbow + self.length_elbow_to_gripper
                ):
                    raise Exception("Coordinates cannot be reached by the Robot")

                theta2_inner = (
                                       (self.destination_coordinate[0] ** 2) + (self.destination_coordinate[1] ** 2) -
                                       (self.length_shoulder_to_elbow ** 2) - (self.length_elbow_to_gripper ** 2)
                               ) / (2 * self.length_shoulder_to_elbow * self.length_elbow_to_gripper)

                if (theta2_inner > 1) or (theta2_inner < -1):
                    raise Exception("Coordinates cannot be reached by the Robot")

                theta2_goal = np.arccos(theta2_inner)
                if theta2_goal < 0:
                    theta1_goal = np.math.atan2(
                        self.destination_coordinate[1],
                        self.destination_coordinate[0]
                    ) + \
                                  np.math.atan2(
                                      self.length_elbow_to_gripper * np.sin(theta2_goal),
                                      (
                                              self.length_shoulder_to_elbow +
                                              self.length_elbow_to_gripper *
                                              np.cos(theta2_goal)
                                      )
                                  )
                else:
                    theta1_goal = np.math.atan2(
                        self.destination_coordinate[1],
                        self.destination_coordinate[0]
                    ) - \
                                  np.math.atan2(
                                      self.length_elbow_to_gripper * np.sin(theta2_goal),
                                      (
                                              self.length_shoulder_to_elbow +
                                              self.length_elbow_to_gripper *
                                              np.cos(theta2_goal)
                                      )
                                  )

                def _angle_difference(theta1, theta2):
                    return (theta1 - theta2 + np.pi) % (2 * np.pi) - np.pi

                self.theta1 = self.theta1 + (
                        self.proportional_gain * _angle_difference(theta1_goal, self.theta1) * self.sample_time
                )
                self.theta2 = self.theta2 + (
                        self.proportional_gain * _angle_difference(theta2_goal, self.theta2) * self.sample_time
                )

                self.previous_destination_coordinate = self.destination_coordinate

                wrist = await self.generate_inverse_kinematics()

                # check goal
                if self.destination_coordinate[0] is not None and self.destination_coordinate[1] is not None:
                    d2goal = np.hypot(
                        wrist[0] - self.destination_coordinate[0],
                        wrist[1] - self.destination_coordinate[1]
                    )

                if abs(d2goal) < self.GOAL_THRESHOLD and self.destination_coordinate[0] is not None:
                    self.get_motion_sequence()

            await asyncio.sleep(self.sample_time)

        except Exception as e:
            logger.error('Exception during updating Arm Movement Data')
            logger.error(e)
            self.destination_coordinate = self.previous_destination_coordinate

    async def generate_inverse_kinematics(self):
        """generate_inverse_kinematics: Ploting inverse kinematics for Robotic Arm
        """
        result = dict()

        elbow = self.shoulder + \
                np.array(
                    [
                        self.length_shoulder_to_elbow * np.cos(self.theta1),
                        self.length_shoulder_to_elbow * np.sin(self.theta1)
                    ]
                )

        wrist = elbow + \
                np.array(
                    [
                        self.length_elbow_to_gripper * np.cos(self.theta1 + self.theta2),
                        self.length_elbow_to_gripper * np.sin(self.theta1 + self.theta2)
                    ]
                )

        result.update(
            {
                "id": self.id,
                "base": self.base.tolist(),
                "shoulder": self.shoulder.tolist(),
                "elbow": elbow.tolist(),
                "wrist": wrist.tolist(),
                "theta1": self.theta1,
                "theta2": self.theta2
            }
        )

        await self.publish(
            exchange_name="telemetry_exchange",
            msg=json.dumps(result).encode()
        )

        wrist[0] -= self.shoulder[0]
        wrist[1] -= self.shoulder[1]
        return wrist

    def get_motion_sequence(self):
        """get_motion_sequence: get motion sequence of the robotic arm"""

        if self.motion_pattern is not None:
            if self.sequence_count >= len(self.motion_pattern):
                self.sequence_count = 0
            self.destination_coordinate = [
                self.motion_pattern[self.sequence_count]["x"],
                self.motion_pattern[self.sequence_count]["y"]
            ]
            self.sequence_count += 1

    def get_forward_kinematics(self):
        """get_forward_kinematics: Forward Kinematics for the Robotic Arm"""
        elbow = self.shoulder + \
                np.array(
                    [
                        self.length_shoulder_to_elbow * np.cos(self.theta1),
                        self.length_shoulder_to_elbow * np.sin(self.theta1)
                    ]
                )

        wrist = elbow + \
                np.array(
                    [
                        self.length_elbow_to_gripper * np.cos(self.theta1 + self.theta2),
                        self.length_elbow_to_gripper * np.sin(self.theta1 + self.theta2)
                    ]
                )

        return dict(
            shoulder=(self.shoulder[0], self.shoulder[1]),
            elbow=(elbow[0], elbow[1]),
            wrist=(wrist[0], wrist[1])
        )

    def __get_all_states__(self):
        logger.debug(vars(self))

    def consume_control_msg(self, **kwargs):
        exchange_name = kwargs["exchange_name"]
        binding_name = kwargs["binding_name"]
        message_body = json.loads(kwargs["message_body"])

        for subscriber in self.subscribers:
            if subscriber.exchange_name == exchange_name:
                if "control.robot" in binding_name:
                    binding_delimited_array = binding_name.split(".")
                    robot_id = binding_delimited_array[len(binding_delimited_array) - 1]
                    msg_attributes = message_body.keys()
                    if ("id" in msg_attributes) and ("control" in msg_attributes):
                        if (robot_id == message_body["id"]) and (robot_id == self.id):
                            logger.debug(message_body)
                            self.update_operation_state(state=message_body["control"])
