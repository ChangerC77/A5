import rclpy
from rclpy.node import Node
from a5_bimanual_arm.bimanual_arm_controller import BimanualArmFSM
from a5_bimanual_arm.keyboard_handler import KeyboardHandler

from message_filters import Subscriber, ApproximateTimeSynchronizer
from sensor_msgs.msg import Image


class BimanualArmControllerNode(Node):

    def __init__(self):
        super().__init__('bimanual_arm_controller')

        self.declare_parameter('mode', 'collect')
        self.declare_parameter('img_head_topic', '/camera_head/image/')
        self.declare_parameter('img_left_topic', '/camera_left/image/')
        self.declare_parameter('img_right_topic', '/camera_right/image/')

        self.arm_mode = self.get_parameter('mode').get_parameter_value().string_value
        if self.arm_mode not in ('collect', 'infer'):
            self.get_logger().error(f"Invalid mode '{self.arm_mode}', must be 'collect' or 'infer'")
            raise ValueError(f"mode must be 'collect' or 'infer', got '{self.arm_mode}'")

        self._fsm = BimanualArmFSM(self.get_logger(), self.arm_mode)

        self._keyboard = KeyboardHandler()
        self._keyboard.add_key_callback('space', self._key_callback)
        self._keyboard.add_key_callback('esc', self._key_callback)
        self._keyboard.start()

        if self.arm_mode == 'collect':
            self._init_realsense_sub()

        self.get_logger().info('BimanualArmController node started.')

    def _key_callback(self, key, state):
        if state != KeyboardHandler.KEY_STATE_PRESSED:
            return
        if key == 'space':
            self._fsm.on_key_event('space')
        elif key == 'esc':
            self._fsm.on_key_event('esc')

    def _init_realsense_sub(self):
        img_head_topic = self.get_parameter('img_head_topic').get_parameter_value().string_value
        img_left_topic = self.get_parameter('img_left_topic').get_parameter_value().string_value
        img_right_topic = self.get_parameter('img_right_topic').get_parameter_value().string_value
        self.head_realsense_sub = Subscriber(self, Image, img_head_topic)
        self.left_realsense_sub = Subscriber(self, Image, img_left_topic)
        self.right_realsense_sub = Subscriber(self, Image, img_right_topic)

        self.sync = ApproximateTimeSynchronizer(
            [self.head_realsense_sub, self.left_realsense_sub, self.right_realsense_sub],
            queue_size=2,
            slop=0.05,
        )
        self.sync.registerCallback(self.realsense_sync_callback)

    def realsense_sync_callback(self, img_head: Image, img_left: Image, img_right: Image):
        self._fsm.record_image("images/head", img_head)
        self._fsm.record_image("images/left_wrist", img_left)
        self._fsm.record_image("images/right_wrist", img_right)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = BimanualArmControllerNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node._fsm.shutdown()
            node._keyboard.stop()
            node.destroy_node()
        rclpy.shutdown()
