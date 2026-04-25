# a5_bimanual_arm

ROS2 (Jazzy) 双臂机械臂控制器包，基于有限状态机（FSM）管理双臂生命周期，支持三种运行模式：

- `collect`：采集关节状态、动作与三路图像并保存为 HDF5
- `infer`：推理占位模式（当前接口保留，逻辑待业务实现）
- `replay`：回放 HDF5 轨迹到双臂关节

## 目录结构

```text
a5_bimanual_arm/
├── a5_bimanual_arm/
│   ├── bimanual_arm_controller.py      # 核心 FSM 控制器
│   ├── bimanual_arm_controller_node.py # ROS2 节点入口
│   ├── recorder.py                      # 采集缓存与 HDF5 保存
│   └── keyboard_handler.py              # SPACE/ESC 键盘输入
├── launch/
│   └── bimanual_arm.launch.py
├── test/
├── package.xml
└── setup.py
```

## 依赖

- ROS2 Jazzy
- `arx_a5_python`（`SingleArm` 硬件接口）
- `transitions`（FSM）
- `message_filters` + `sensor_msgs`（图像同步）
- `h5py`, `numpy`, `cv_bridge`

## 构建

先确保工作区里 `arx_a5_python` 已完成 C++ 绑定编译（见工作区根目录 `AGENTS.md`）。

```bash
source /opt/ros/jazzy/setup.bash
cd /path/to/A5
colcon build --packages-select arx_a5_python a5_bimanual_arm
source install/setup.bash
```

## 运行

### 1) collect（数据采集）

```bash
ros2 run a5_bimanual_arm bimanual_arm_controller --ros-args \
  -p mode:=collect \
  -p datasets_dir:=/path/to/datasets
```

### 2) infer（推理模式，占位）

```bash
ros2 run a5_bimanual_arm bimanual_arm_controller --ros-args -p mode:=infer
```

### 3) replay（轨迹回放）

默认策略：若不指定回放文件，则自动选择 `datasets_dir` 下最新的 `episode_*.hdf5`，回放 `data/demo_0`，播完自动回到 `homing -> ready`。

```bash
ros2 run a5_bimanual_arm bimanual_arm_controller --ros-args \
  -p mode:=replay \
  -p datasets_dir:=/home/arx/WBCD/A5/datasets
```

也可显式指定文件与 demo 索引：

```bash
ros2 run a5_bimanual_arm bimanual_arm_controller --ros-args \
  -p mode:=replay \
  -p replay_hdf5_path:=/home/arx/WBCD/A5/datasets/episode_0.hdf5 \
  -p replay_demo_index:=0
```

### 4) 使用 launch

```bash
ros2 launch a5_bimanual_arm bimanual_arm.launch.py mode:=collect
```

## FSM 状态机

状态流转：

```text
initialized -> homing -> ready -> collecting/inferring/replaying -> homing -> ...
```

状态说明：

- `initialized`：初始状态
- `homing`：回零并等待固定时长（默认 3 秒）
- `ready`：等待用户触发任务
- `collecting`：数据采集
- `inferring`：推理占位
- `replaying`：轨迹回放

键盘事件：

- `SPACE`：`ready` 下开始任务；任务中（`collecting`/`inferring`/`replaying`）结束任务
- `ESC`：停止控制循环并关停节点

## 控制循环

控制线程以 30 Hz 运行，每帧执行：

1. 处理键盘事件队列
2. 处理自动状态转换（`homing` 超时）
3. 执行状态动作：
   - `collecting`: `_collect_step()`
   - `inferring`: `_infer_step()`
   - `replaying`: `_replay_step()`
   - 其他状态: 重力补偿

## ROS 参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `mode` | `collect` | 运行模式：`collect` / `infer` / `replay` |
| `datasets_dir` | `./datasets` | 采集保存目录；replay 自动找最新文件时也使用该目录 |
| `replay_hdf5_path` | `""` | replay 文件路径；为空时自动选择最新 `episode_*.hdf5` |
| `replay_demo_index` | `0` | replay 使用的 `data/demo_x` 索引 |
| `img_head_topic` | `/camera_head/image` | 头部相机话题（collect 模式） |
| `img_left_topic` | `/camera_left/image` | 左腕相机话题（collect 模式） |
| `img_right_topic` | `/camera_right/image` | 右腕相机话题（collect 模式） |

说明：图像订阅仅在 `collect` 模式启用。

## replay 数据格式约定

回放读取 `data/demo_x`：

- 优先读取 `actions`（形状需为 `N x 14`）
- 若无 `actions`，回退读取 `observations/qpos`（`N x 14`）
- 时间优先读取 `timestamp`；若缺失或非法则回退为 30 Hz

回放会按时间戳推进发送关节目标，左右臂各 7 维。

## 硬件配置

默认 CAN 端口：

- 左臂：`can1`
- 右臂：`can3`

URDF：`a5.urdf`

CAN 规则与接口配置请参考工作区根目录 `AGENTS.md`。

## 常见问题

- 启动报 `mode` 非法：确认参数是 `collect` / `infer` / `replay` 之一
- replay 提示找不到文件：检查 `datasets_dir` 下是否存在 `episode_*.hdf5`，或直接传 `replay_hdf5_path`
- replay 提示 shape 不合法：确保 `actions` 或 `observations/qpos` 是 `N x 14`
- 采集模式无图像：检查话题名和 QoS（代码使用 `qos_profile_sensor_data`）
