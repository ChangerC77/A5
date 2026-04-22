import rclpy
from rclpy.node import Node
from arx_a5_python import SingleArm
from typing import Dict, Any
import numpy as np
import time
import threading
from sensor_msgs.msg import  CompressedImage
from collections import deque

class BimanualArmController(Node):

    def __init__(self):
        super().__init__('bimanual_arm_controller')
        self.get_logger().info('BimanualArmController node started.')
        # attr
        self.img_head_deque = deque()
        self.img_left_deque = deque()
        self.img_right_deque = deque()

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
        
        self._ctrl_running = True
        self._ctrl_thread = threading.Thread(target=self._control_loop, daemon=True)
        self._ctrl_thread.start()

    def _control_loop(self):
        period = 1.0 / 100.0
        self.get_logger().info('Control loop started at 100Hz.')
        while self._ctrl_running:
            t0 = time.perf_counter()
            try:
                self.left_arm.gravity_compensation()
                self.right_arm.gravity_compensation()
            except Exception as e:
                self.get_logger().error(f'Control loop error: {e}')
                break
            elapsed = time.perf_counter() - t0
            sleep_time = period - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    def _startup_arms(self):
        arm_config_0: Dict[str, Any] = {
        "can_port": "can1",
        "urdf_name": "a5.urdf",
        # Add necessary configuration parameters for the left arm
        }

        arm_config_1: Dict[str, Any] = {
        "can_port": "can3",
        "urdf_name": "a5.urdf",
        # Add necessary configuration parameters for the right arm
        }
        self.left_arm = SingleArm(arm_config_0)
        self.right_arm = SingleArm(arm_config_1)

    def _img_head_callback(self, msg: CompressedImage):
        self.img_head_deque.pop(msg)

    def _img_left_callback(self, msg: CompressedImage):
        ...

    def _img_right_callback(self, msg: CompressedImage):
        ...



def main(args=None):
    rclpy.init(args=args)
    node = BimanualArmController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node._ctrl_running = False
        node._ctrl_thread.join(timeout=1.0)
        node.destroy_node()
        rclpy.shutdown()
