import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from a5_bimanual_arm.bimanual_arm_controller import BimanualArmFSM
from a5_bimanual_arm.keyboard_handler import KeyboardHandler

from message_filters import Subscriber, ApproximateTimeSynchronizer
from sensor_msgs.msg import Image


class BimanualArmControllerNode(Node):

    def __init__(self):
        super().__init__('bimanual_arm_controller')

        self.declare_parameter('mode', 'collect')
        self.declare_parameter('datasets_dir', './datasets')
        self.declare_parameter('img_head_topic', '/camera_head/image')
        self.declare_parameter('img_left_topic', '/camera_left/image')
        self.declare_parameter('img_right_topic', '/camera_right/image')

        self.arm_mode = self.get_parameter('mode').get_parameter_value().string_value
        if self.arm_mode not in ('collect', 'infer'):
            self.get_logger().error(f"Invalid mode '{self.arm_mode}', must be 'collect' or 'infer'")
            raise ValueError(f"mode must be 'collect' or 'infer', got '{self.arm_mode}'")

        datasets_dir = self.get_parameter('datasets_dir').get_parameter_value().string_value
        self._fsm = BimanualArmFSM(
            self.get_logger(),
            self.arm_mode,
            datasets_dir=datasets_dir,
        )

        self._keyboard = KeyboardHandler()
        self._keyboard.add_key_callback('space', self._key_callback)
        self._keyboard.add_key_callback('esc', self._key_callback)
        self._keyboard.start()

        if self.arm_mode == 'collect':
            self._img_recv_count = {'head': 0, 'left': 0, 'right': 0}
            self._sync_count = 0
            self._debug_timer = self.create_timer(2.0, self._report_realsense_stats)
            self._init_realsense_sub()

        self.get_logger().info(f'Mode: {self.arm_mode}, datasets_dir: {datasets_dir}')
        self.get_logger().info('BimanualArmController node started.')

    def _key_callback(self, key, state):

        if state != KeyboardHandler.KEY_STATE_PRESSED:
            return
        self.get_logger().info(f'Key pressed: {key}')
        if key == 'space':
            self._fsm.on_key_event('space')
        elif key == 'esc':
            self._fsm.on_key_event('esc')
        

    def _init_realsense_sub(self):
        img_head_topic = self.get_parameter('img_head_topic').get_parameter_value().string_value.rstrip('/')
        img_left_topic = self.get_parameter('img_left_topic').get_parameter_value().string_value.rstrip('/')
        img_right_topic = self.get_parameter('img_right_topic').get_parameter_value().string_value.rstrip('/')

        self.get_logger().info(
            'Init image sync subscribers: '
            f'head={img_head_topic}, left={img_left_topic}, right={img_right_topic}, '
            'qos=sensor_data(best_effort), slop=0.05'
        )

        self.head_realsense_sub = Subscriber(self, Image, img_head_topic, qos_profile=qos_profile_sensor_data)
        self.left_realsense_sub = Subscriber(self, Image, img_left_topic, qos_profile=qos_profile_sensor_data)
        self.right_realsense_sub = Subscriber(self, Image, img_right_topic, qos_profile=qos_profile_sensor_data)

        self.head_realsense_sub.registerCallback(self._on_head_image)
        self.left_realsense_sub.registerCallback(self._on_left_image)
        self.right_realsense_sub.registerCallback(self._on_right_image)

        self.sync = ApproximateTimeSynchronizer(
            [self.head_realsense_sub, self.left_realsense_sub, self.right_realsense_sub],
            queue_size=2,
            slop=0.05,
        )
        self.sync.registerCallback(self.realsense_sync_callback)

    def _on_head_image(self, _msg: Image):
        self._img_recv_count['head'] += 1

    def _on_left_image(self, _msg: Image):
        self._img_recv_count['left'] += 1

    def _on_right_image(self, _msg: Image):
        self._img_recv_count['right'] += 1

    def _report_realsense_stats(self):
        if self.arm_mode != 'collect':
            return
        self.get_logger().debug(
            f"Image receive stats: head={self._img_recv_count['head']}, "
            f"left={self._img_recv_count['left']}, right={self._img_recv_count['right']}, "
            f"synced={self._sync_count}"
        )
        if any(v == 0 for v in self._img_recv_count.values()):
            self.get_logger().warning(
                'No image received on one or more topics yet. '
                'Check topic names and publisher QoS compatibility.'
            )

    def realsense_sync_callback(self, img_head: Image, img_left: Image, img_right: Image):
        self._sync_count += 1
        self.get_logger().debug(
            f'Sync callback #{self._sync_count} '
            f"head={img_head.header.stamp.sec}.{img_head.header.stamp.nanosec:09d}, "
            f"left={img_left.header.stamp.sec}.{img_left.header.stamp.nanosec:09d}, "
            f"right={img_right.header.stamp.sec}.{img_right.header.stamp.nanosec:09d}"
        )
        self._fsm.record_image("images/head", img_head)
        self._fsm.record_image("images/left_wrist", img_left)
        self._fsm.record_image("images/right_wrist", img_right)
        # self.get_logger().info(f'Image synced: #{self._sync_count}')


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
