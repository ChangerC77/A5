# A5 Bimanual Arm Workspace

ROS2 (Jazzy) workspace for ARX A5 双臂机械臂控制与数据采集。

## 包结构

| 目录 | 说明 | 构建类型 |
|---|---|---|
| `arx_a5_python/` | pybind11 Python 绑定（SingleArm, FK/IK） | ament_python（含 C++ 子模块） |
| `a5_bimanual_arm/` | ROS2 双臂控制器节点（FSM） | ament_python |
| `transmission/` | ZMQ 桥接（远程控制） | 纯 Python，不参与 colcon |
| `collect.py` | 数据采集脚本（HDF5） | 独立脚本 |

依赖关系：`a5_bimanual_arm` → `arx_a5_python`

## 构建

```bash
source /opt/ros/jazzy/setup.bash

# 1. 编译 C++ pybind 模块（必须先于 colcon）
cd arx_a5_python/cpp && ./build.sh

# 2. colcon 构建 ROS2 包
cd /path/to/A5
colcon build --packages-select arx_a5_python a5_bimanual_arm
```

**必须用 `/usr/bin/python3` 编译 C++ 模块**，`arx_a5_python/cpp/build.sh` 已强制此配置。使用 conda Python 编译会导致 .so 版本不匹配。

## CAN 总线

双臂通过 CAN 通信：左臂 can1，右臂 can3。首次使用需配置：

```bash
cd ARX_CAN && ./search    # 查找设备序列号
# 编辑 ARX_CAN/arx_can.rules 填入序列号
sudo cp arx_can.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
cd ARX_CAN && ./set        # 配置 CAN 接口
./arx_can1                 # 启动 can1（左臂）
```

## 运行

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run a5_bimanual_arm bimanual_arm_controller --ros-args -p mode:=collect
```

## 关键依赖

- `transitions` — Python 状态机（`a5_bimanual_arm` 的 FSM）
- `pyzmq` — ZMQ 通信（`transmission/`）
- `pybind11 3.1+` — C++ 绑定编译
- `h5py`, `cv2`, `pyttsx3` — 数据采集脚本

## 详细文档

`arx_a5_python/AGENTS.md` 包含该包的完整 API、目录结构、加载机制和常见问题排查。
