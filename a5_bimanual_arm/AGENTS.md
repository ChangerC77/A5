# a5_bimanual_arm

ROS2 (Jazzy) 双臂机械臂控制器包，基于有限状态机（FSM）管理双臂生命周期。

## 目录结构

```
a5_bimanual_arm/
├── a5_bimanual_arm/
│   ├── __init__.py
│   ├── bimanual_arm_controller.py      # 核心 FSM 控制器
│   └── bimanual_arm_controller_node.py # ROS2 节点入口
├── launch/                             # launch 文件（暂空）
├── resource/
├── test/
│   ├── test_copyright.py
│   ├── test_flake8.py
│   └── test_pep257.py
├── package.xml
├── setup.cfg
└── setup.py
```

## 构建

```bash
source /opt/ros/jazzy/setup.bash
cd /path/to/A5
colcon build --packages-select a5_bimanual_arm
```

依赖 `arx_a5_python` 包，需先构建该包（见工作区根目录 `AGENTS.md`）。

## 运行

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run a5_bimanual_arm bimanual_arm_controller --ros-args -p mode:=collect
```

`mode` 参数：`collect`（数据采集）或 `infer`（推理）。

## 架构

### 状态机（BimanualArmFSM）

`bimanual_arm_controller.py` 中的 `BimanualArmFSM` 类基于 `transitions` 库实现。

**状态流转：**

```
initialized → homing → ready → collecting/inferring → homing → ...
                                ↑_________________________|
```

| 状态 | 说明 |
|---|---|
| `initialized` | 初始状态，创建硬件连接后自动进入 homing |
| `homing` | 回零，等待 3 秒后自动转到 ready |
| `ready` | 等待用户按键 |
| `collecting` | 数据采集模式下的任务执行 |
| `inferring` | 推理模式下的任务执行 |

**键盘交互：**
- `SPACE` — ready 状态下开始任务；collecting/inferring 状态下结束任务
- `ESC` — 关停控制器

### 控制循环

独立线程以 30Hz 运行，每帧执行：
1. 处理事件队列（键盘输入）
2. 处理自动状态转换（homing 超时）
3. 执行当前状态的动作步骤（`_collect_step` / `_infer_step` / `_gravity_compensation`）

### ROS2 节点（BimanualArmControllerNode）

`bimanual_arm_controller_node.py` 封装 FSM 为 ROS2 节点。

**ROS 参数：**

| 参数 | 默认值 | 说明 |
|---|---|---|
| `mode` | `collect` | 运行模式 |
| `img_head_topic` | `/camera_head/image/` | 头部相机话题 |
| `img_left_topic` | `/camera_left/image/` | 左相机话题 |
| `img_right_topic` | `/camera_right/image/` | 右相机话题 |

**图像订阅：** 通过 `ApproximateTimeSynchronizer` 同步三路 RealSense 图像（50ms 容差），回调 `realsense_sync_callback` 待实现。

## 硬件配置

| 臂 | CAN 端口 | URDF |
|---|---|---|
| 左臂 | `can1` | `a5.urdf` |
| 右臂 | `can3` | `a5.urdf` |

## 依赖

- `arx_a5_python` — SingleArm 硬件接口（pybind11）
- `transitions` — Python 状态机库
- `rclpy` — ROS2 Python 客户端
- `message_filters` — ROS2 消息同步

## 待实现

以下方法为占位符，需按业务需求补充：
- `_init_collect()` / `_collect_step()` — 数据采集逻辑
- `_init_infer()` / `_infer_step()` — 推理逻辑
- `realsense_sync_callback()` — 图像同步回调

## 注意事项

- `get_joint_positions()` / `get_joint_velocities()` 中索引计算 `self._joint_num/2` 结果为 float，需确认逻辑正确性（7 个关节 x 2 臂 = 14）
- 控制线程异常会导致退出循环，不会自动恢复
- CAN 总线配置见工作区根目录 `AGENTS.md`
