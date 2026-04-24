import rclpy
from rclpy.node import Node
from arx_a5_python import SingleArm
from typing import Dict, Any
import numpy as np
import time
import threading
from sensor_msgs.msg import  CompressedImage
from collections import deque
from enum import Enum, unique



class BimanualArmControllerNode(Node):

    def __init__(self):
        super().__init__('bimanual_arm_controller')
        self.get_logger().info('BimanualArmController node started.')
        # attr

        # declare params
        self.declare_parameter('img_head_topic', '/camera_head/image/compressed')
        self.declare_parameter('img_left_topic', '/camera_left/image/compressed')
        self.declare_parameter('img_right_topic', '/camera_right/image/compressed')

        # read params
        img_head_topic = self.get_parameter('img_head_topic').get_parameter_value().string_value
        img_left_topic = self.get_parameter('img_left_topic').get_parameter_value().string_value
        img_right_topic = self.get_parameter('img_right_topic').get_parameter_value().string_value

        # img subscription
        self._img_deques: Dict[str, deque] = {
            'img_head': self.img_head_deque,
            'img_left': self.img_left_deque,
            'img_right': self.img_right_deque,
        }
        img_topics = {
            'img_head': img_head_topic,
            'img_left': img_left_topic,
            'img_right': img_right_topic,
        }
        for key, topic in img_topics.items():
            try:
                callback = getattr(self, f'_{key}_callback')
                self.create_subscription(CompressedImage, topic, callback, 10)
            except KeyError as e:
                self.get_logger().error(f"Topic config missing: {e}")
            except AttributeError as e:
                self.get_logger().error(f"Callback not found for key: {key} -> {e}")
        
        # 启动机械臂
        try:
            self._startup_arms()
        except Exception as e:
            self.get_logger().fatal(f'Failed to startup arms: {e}')
            raise
        


    def _img_head_callback(self, msg: CompressedImage):
        self.img_head_deque.pop(msg)

    def _img_left_callback(self, msg: CompressedImage):
        ...

    def _img_right_callback(self, msg: CompressedImage):
        ...



def main(args=None):
    rclpy.init(args=args)
    node = BimanualArmControllerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node._ctrl_running = False
        node._ctrl_thread.join(timeout=1.0)
        node.destroy_node()
        rclpy.shutdown()
