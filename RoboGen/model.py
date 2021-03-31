"""
Inverse kinematics of a two-joint arm
Left-click the plot to set the goal position of the end effector

Author: Daniel Ingram (daniel-s-ingram)
        Atsushi Sakai (@Atsushi_twi)

Ref: [P. I. Corke, "Robotics, Vision & Control",
    Springer 2017, ISBN 978-3-319-54413-7 p102](https://link.springer.com/book/10.1007/978-3-642-20144-8)

Authors:
    Karthik <she@biba.uni-bremen.de>
        update-1:Dec-06-2020 :Converted the Original function implementation to class based implementation
    Shantanoo <des@biba.uni-bremen.de, shantanoo.desai@gmail.com>
        update-2:Mar-03-2021 :Apply Linting on File, remove unused imports and variables
"""
import asyncio
import json
import logging
import math
import os
import sys
import traceback

import numpy as np
import yaml

from .AMQPubSub import AMQ_Pub_Sub

logging.basicConfig(
    level=logging.WARNING,
    format='%(levelname)-8s [%(filename)s:%(lineno)d] %(message)s'
)


class RobotArm2:
    """This class implements Robot Arm with 2 joint ARM
    """

    def __init__(self, event_loop, config_file, robot_id):
        try:
            robot_conf = config_file["robot"]
            sequence_conf = config_file["sequence"]
            amq_config = config_file["amq"]

            # The personnel id of instance must be specified in yaml config file.
            # If not raise Assertion error
            robot_info = None
            for robot in robot_conf:
                if robot["id"] == robot_id:
                    robot_info = robot
                    break
            assert (robot_info is not None), \
                f"robot_id: {robot_id} does not exists in configuration file"

            self.id = robot_info["id"]
            self.proportional_gain = robot_info["motion"]["control"]["proportional_gain"]
            self.sample_time = robot_info["motion"]["control"]["sample_rate"]
            self.length_shoulder_to_elbow = robot_info["arm"]["length"]["shoulder_to_elbow"]
            self.length_elbow_to_gripper = robot_info["arm"]["length"]["elbow_to_gripper"]
            self.shoulder = np.array(robot_info["initial_position"]["base"])
            self.motion_pattern = None
            for seq in sequence_conf:
                if seq["name"] == robot_info["motion"]["pattern"]:
                    self.motion_pattern = seq["pattern"]

            self.theta1 = 0.0
            self.theta2 = 0.0
            self.GOAL_THRESHOLD = 0.01

            self.destination_coordinate = [0,0]
            self.previous_destination_coordinate = self.destination_coordinate

            self.sequence_count = 0

            self.eventloop = event_loop
            self.publisher = AMQ_Pub_Sub(
                eventloop=self.eventloop,
                config_file=amq_config,
                pub_sub_name=robot_info["pub_sub_mapping"]["publisher"],
                mode="pub"
            )
        except FileNotFoundError as e:
            logging.critical(e)
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logging.critical(
                repr(
                    traceback.format_exception(
                        exc_type,
                        exc_value,
                        exc_traceback)
                )
            )
            sys.exit()
        except OSError as e:
            logging.critical(e)
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logging.critical(
                repr(
                    traceback.format_exception(
                        exc_type,
                        exc_value,
                        exc_traceback
                    )
                )
            )
            sys.exit()
        except AssertionError as e:
            logging.critical(e)
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logging.critical(
                repr(
                    traceback.format_exception(
                        exc_type,
                        exc_value,
                        exc_traceback
                    )
                )
            )
            sys.exit()
        except yaml.YAMLError as e:
            logging.critical(e)
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logging.critical(
                repr(
                    traceback.format_exception(
                        exc_type,
                        exc_value,
                        exc_traceback
                    )
                )
            )
            sys.exit()
        except Exception:
            logging.critical("unhandled exception")
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logging.critical(
                repr(
                    traceback.format_exception(
                        exc_type,
                        exc_value,
                        exc_traceback
                    )
                )
            )
            sys.exit()

    async def publish(self, binding_key, msg):
        await self.publisher.publish(
            binding_key=binding_key,
            message_content=msg
        )

    async def connect(self):
        await self.publisher.connect()

    async def update(self):
        """Computes the inverse kinematics for a planar 2DOF arm.
        When out of bounds, rewrite x and y with last correct values

        Returns:
            [type]: [description]
        """
        try:
            if math.sqrt(
                (self.destination_coordinate[0] ** 2) +
                (self.destination_coordinate[1] ** 2)
                ) > (
                    self.length_shoulder_to_elbow + self.length_elbow_to_gripper
                    ):
                raise RuntimeError("Coordinates cannot be reached by the Robot")

            theta2_inner = (
                    (self.destination_coordinate[0] ** 2) + (self.destination_coordinate[1] ** 2) -
                    (self.length_shoulder_to_elbow ** 2) - (self.length_elbow_to_gripper ** 2)
                ) \
                / (2 * self.length_shoulder_to_elbow * self.length_elbow_to_gripper)

            if (theta2_inner > 1) or (theta2_inner < -1):
                raise RuntimeError("Coordinates cannot be reached by the Robot")

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

            def angle_difference(theta1, theta2):
                return (theta1 - theta2 + np.pi) % (2 * np.pi) - np.pi

            self.theta1 = self.theta1 + self.proportional_gain * angle_difference(theta1_goal, self.theta1) * self.sample_time
            self.theta2 = self.theta2 + self.proportional_gain * angle_difference(theta2_goal, self.theta2) * self.sample_time

            self.previous_destination_coordinate = self.destination_coordinate

            wrist = await self.generate_joint_coordinates()

            # check goal
            if self.destination_coordinate[0] is not None and self.destination_coordinate[1] is not None:
                d2goal = np.hypot(
                    wrist[0] - self.destination_coordinate[0],
                    wrist[1] - self.destination_coordinate[1]
                )

            if abs(d2goal) < self.GOAL_THRESHOLD and self.destination_coordinate[0] is not None:
                self.get_motion_sequence()

            await asyncio.sleep(self.sample_time)

        except ValueError as e:
            logging.critical(e)
            exit(-1)
        except TypeError as e:
            logging.critical(e)
            exit(-1)
        except RuntimeError as e:
            logging.critical(e)
            self.destination_coordinate = self.previous_destination_coordinate

    async def generate_joint_coordinates(self):  # pragma: no cover
        """Ploting arm

            Returns:
                [type]: [description]
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
                "shoulder": np.array2string(self.shoulder),
                "elbow": np.array2string(elbow),
                "wrist": np.array2string(wrist),
                "theta1": self.theta1,
                "theta2": self.theta2
            }
        )

        await self.publish(
            binding_key="telemetry",
            msg=json.dumps(result).encode()
        )

        wrist[0] -= self.shoulder[0]
        wrist[1] -= self.shoulder[1]
        return wrist

    def get_motion_sequence(self):
        if self.motion_pattern is not None:
            if self.sequence_count >= len(self.motion_pattern):
                self.sequence_count = 0
            self.destination_coordinate = self.motion_pattern[self.sequence_count]["position"]
            self.sequence_count += 1

    def get_joint_coordinates(self):
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
        logging.debug(vars(self))


if __name__ == "__main__":

    async def test(eventloop):
        robo = RobotArm2(
            event_loop=event_loop,
            config_file="robot.yaml",
            robot_id=1
            )

        await robo.connect()
        while True:
            await robo.update()

    event_loop = asyncio.get_event_loop()
    event_loop.run_until_complete(test(event_loop))
