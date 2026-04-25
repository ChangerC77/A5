from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    mode_arg = DeclareLaunchArgument(
        'mode',
        default_value='collect',
        description='Running mode: collect or infer'
    )
    img_head_topic_arg = DeclareLaunchArgument(
        'img_head_topic',
        default_value='/camera_head/image/',
        description='Head camera image topic'
    )
    img_left_topic_arg = DeclareLaunchArgument(
        'img_left_topic',
        default_value='/camera_left/image/',
        description='Left wrist camera image topic'
    )
    img_right_topic_arg = DeclareLaunchArgument(
        'img_right_topic',
        default_value='/camera_right/image/',
        description='Right wrist camera image topic'
    )

    bimanual_arm_node = Node(
        package='a5_bimanual_arm',
        executable='bimanual_arm_controller',
        name='bimanual_arm_controller',
        output='screen',
        parameters=[{
            'mode': LaunchConfiguration('mode'),
            'img_head_topic': LaunchConfiguration('img_head_topic'),
            'img_left_topic': LaunchConfiguration('img_left_topic'),
            'img_right_topic': LaunchConfiguration('img_right_topic'),
        }]
    )

    return LaunchDescription([
        mode_arg,
        img_head_topic_arg,
        img_left_topic_arg,
        img_right_topic_arg,
        bimanual_arm_node,
    ])