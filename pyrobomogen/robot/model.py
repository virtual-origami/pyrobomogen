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
import time
import traceback

import numpy as np
from pyrobomogen.watchdog_timer import WDT

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
            self.sample_interval = robot_info["motion"]["control"]["sample_interval"]
            self.length_shoulder_to_elbow = robot_info["arm"]["length"]["shoulder_to_elbow"]
            self.length_elbow_to_gripper = robot_info["arm"]["length"]["elbow_to_gripper"]
            self.base = np.array(
                [robot_info["base"]["x"], robot_info["base"]["y"]]
            )
            self.shoulder = np.array(
                [robot_info["shoulder"]["x"], robot_info["shoulder"]["y"]]
            )
            self.motion_pattern = robot_info["motion"]["pattern"]["task_coordinates"]

            self.theta1 = 0.0
            self.theta2 = 0.0
            self.GOAL_THRESHOLD = robot_info["motion"]["control"]["goal_threshold"]

            self.destination_coordinate = [0, 0]
            self.previous_destination_coordinate = self.destination_coordinate
            self.generator_result = None
            self.visual_result = None
            self.sequence_count = 0

            self.eventloop = event_loop
            self.control = "start"
            self.prev_control = self.control
            self.wdt = WDT(check_interval_sec=0.1, trigger_delta_sec=5, callback=self.wdt_cb)
            logger.debug(
                f'Initial Values: Theta1={self.theta1}, Theta2={self.theta2}, GOAL_THRESHOLD={self.GOAL_THRESHOLD}')
            logger.debug(
                f'Initial Values: Previous Destination Coordinates Set to: {self.previous_destination_coordinate}')

        except Exception as e:
            logger.error("Exception during creation of RobotArm2", e)
            sys.exit(-1)

    def update_operation_state(self, state):
        if state == "start":
            self.control = "start"
        elif state == "stop":
            self.control = "stop"
        elif state == "off":
            self.control = "off"
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
                        self.proportional_gain * _angle_difference(theta1_goal, self.theta1) * self.sample_interval
                )
                self.theta2 = self.theta2 + (
                        self.proportional_gain * _angle_difference(theta2_goal, self.theta2) * self.sample_interval
                )

                self.previous_destination_coordinate = self.destination_coordinate

                res = await self.get_wrist()
                wrist = res[0]
                elbow = res[1]

                # check goal
                if self.destination_coordinate[0] is not None and self.destination_coordinate[1] is not None:
                    d2goal = np.hypot(
                        wrist[0] - self.destination_coordinate[0] - self.shoulder[0],
                        wrist[1] - self.destination_coordinate[1] - self.shoulder[1]
                    )

                if abs(d2goal) < self.GOAL_THRESHOLD and self.destination_coordinate[0] is not None:
                    self.get_motion_sequence()

                self.generator_result = {
                    "id": self.id,
                    "base": self.base.tolist(),
                    "shoulder": self.shoulder.tolist(),
                    "theta1": self.theta1,
                    "theta2": self.theta2,
                    "timestamp": time.time_ns(),
                }
                self.visual_result = {
                    "id": self.id,
                    "base": self.base.tolist(),
                    "shoulder": self.shoulder.tolist(),
                    "elbow": elbow.tolist(),
                    "wrist": wrist.tolist(),
                    "theta1": self.theta1,
                    "theta2": self.theta2,
                    "timestamp": time.time_ns(),
                }

                self.wdt.update()
            else:
                self.generator_result = None
                self.visual_result = None

        except Exception as e:
            logger.error('Exception during updating Arm Movement Data')
            logger.error(traceback.print_exc())
            self.destination_coordinate = self.previous_destination_coordinate

    async def get_wrist(self):
        """generate_inverse_kinematics: Ploting inverse kinematics for Robotic Arm
        """

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

        return [wrist, elbow]

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
            elbow=elbow.tolist(),
            wrist=wrist.tolist()
        )

    def __get_all_states__(self):
        logger.debug(vars(self))

    def control_msg_handler(self, message_body):
        self.update_operation_state(state=message_body["control"])
        self.wdt.update()
        self.wdt.resume()

    def wdt_cb(self, wdt):
        wdt.pause()
        if self.control != "off":
            self.update_operation_state(state="start")
            logger.debug(f'WDT: Robot: {self.id} started again')

