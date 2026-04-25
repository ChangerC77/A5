import rclpy
from rclpy.node import Node
from bimanual_arm_controller import BimanualArmFSM

from message_filters import Subscriber, ApproximateTimeSynchronizer
from sensor_msgs.msg import  Image
from collections import deque
from enum import Enum, unique



class BimanualArmControllerNode(Node):

    def __init__(self):
        super().__init__('bimanual_arm_controller')

        # declare params
        self.declare_parameter('mode', 'collect')
        self.declare_parameter('img_head_topic', '/camera_head/image/')
        self.declare_parameter('img_left_topic', '/camera_left/image/')
        self.declare_parameter('img_right_topic', '/camera_right/image/')

        # read params
        self.arm_mode = self.get_parameter('mode').get_parameter_value().string_value

        self._fsm=BimanualArmFSM(self.get_logger(),self.arm_mode)
        self.get_logger().info('BimanualArmController node started.')
        
    def _init_realsense_sub(self):
        img_head_topic = self.get_parameter('img_head_topic').get_parameter_value().string_value
        img_left_topic = self.get_parameter('img_left_topic').get_parameter_value().string_value
        img_right_topic = self.get_parameter('img_right_topic').get_parameter_value().string_value
        self.head_realsense_sub=Subscriber(self,Image, img_head_topic)
        self.left_realsense_sub=Subscriber(self,Image, img_left_topic)
        self.right_realsense_sub=Subscriber(self,Image, img_right_topic)        

        self.sync = ApproximateTimeSynchronizer(
            [self.head_realsense_sub,  self.left_realsense_sub, self.right_realsense_sub],
            queue_size=2,
            slop=0.05  # 50ms容差
        )
        self.sync.registerCallback(self.realsense_sync_callback)

    def realsense_sync_callback(self,img1: Image, img2: Image, img3: Image):
        pass




def main(args=None):
    rclpy.init(args=args)
    node = BimanualArmControllerNode()
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
