# arx_a5_python

ARX A5 机械臂 Python 绑定与控制接口，基于 pybind11 封装 C++ 库，提供 ROS2 ament_python 包。

## 目录结构

```
arx_a5_python/
├── package.xml                  # ROS2 包描述（ament_python build type）
├── setup.py                     # Python 包安装配置
├── setup.cfg                    # setuptools 配置
├── resource/
│   └── arx_a5_python            # ament_python 资源标记文件
├── arx_a5_python/               # Python 包（colcon install 后可 import）
│   ├── __init__.py              # 入口：自动查找 lib/*.so，预加载依赖库，导出类
│   ├── single_arm.py            # SingleArm 单臂控制类
│   ├── dual_arm.py              # BimanualArm 双臂控制类
│   ├── solver.py                # forward/inverse kinematics 封装
│   ├── urdf/                    # URDF 模型文件
│   │   ├── a5.urdf
│   │   └── a5_head.urdf
│   └── lib/                     # pybind11 编译产物（由 cpp/build.sh 生成）
│       ├── arx_a5.cpython-312-x86_64-linux-gnu.so
│       ├── kinematic_solver.cpython-312-x86_64-linux-gnu.so
│       ├── libarx_r5a_src.so
│       └── libkinematic_solver.so
└── cpp/                         # C++ 源码与编译依赖（独立编译，不参与 colcon build）
    ├── CMakeLists.txt            # pybind11 编译，install 目标指向 ../arx_a5_python/lib/
    ├── build.sh                  # 一键编译脚本
    ├── src/
    │   ├── single_arm_interface.cpp   # 单臂接口 pybind 绑定
    │   └── kinematic_solver.cpp       # 运动学求解器 pybind 绑定
    └── lib/                           # 编译依赖（头文件 + 预编译 .so）
        ├── arx_r5_src/                # ARX R5 C++ 源码头文件与库
        ├── arx_hardware_interface/    # 硬件接口头文件
        ├── kinematic_solver.hpp
        └── libkinematic_solver.so
```

## 构建流程

构建分两步：先编译 C++ pybind 模块，再 colcon 构建 ROS2 包。

```bash
# 1. 编译 C++ pybind 模块（生成 .so 到 arx_a5_python/lib/）
cd arx_a5_python/cpp && ./build.sh

# 2. colcon 构建 ROS2 包
cd /home/tony/A5 && colcon build --packages-select arx_a5_python
```

**注意**：`cpp/build.sh` 强制使用 `/usr/bin/python3`（系统 Python）编译，以确保与 ROS2 的 Python 版本一致。不要用 conda Python 编译。

## 使用方式

```bash
source /opt/ros/jazzy/setup.bash
source /home/tony/A5/install/setup.bash
```

```python
from arx_a5_python import SingleArm, BimanualArm, forward_kinematics, inverse_kinematics

# 单臂控制
arm = SingleArm({"can_port": "can0", "urdf_name": "a5.urdf"})
arm.go_home()
arm.set_joint_positions([0.0] * 6)
arm.set_ee_pose(pos=[0.3, 0.0, 0.2], quat=[1, 0, 0, 0])
positions = arm.get_joint_positions()

# 双臂控制
bimanual = BimanualArm(
    left_arm_config={"can_port": "can0", "urdf_name": "a5.urdf"},
    right_arm_config={"can_port": "can1", "urdf_name": "a5.urdf"},
)
bimanual.go_home()

# 运动学求解
import numpy as np
fk_result = forward_kinematics(np.zeros(6))
ik_result = inverse_kinematics(np.zeros(6))
```

## 导出的 API

| 符号 | 来源文件 | 说明 |
|---|---|---|
| `SingleArm` | `single_arm.py` | 单臂控制类 |
| `BimanualArm` | `dual_arm.py` | 双臂控制类 |
| `forward_kinematics` | `solver.py` | 正运动学 |
| `inverse_kinematics` | `solver.py` | 逆运动学 |

## __init__.py 加载机制

1. 定位 `lib/` 目录（相对于包安装路径）
2. 将 `lib/` 添加到 `sys.path` 和 `LD_LIBRARY_PATH`
3. 用 `ctypes.CDLL(mode=RTLD_GLOBAL)` 预加载非 Python 的原生 .so 依赖（`libarx_r5a_src.so`、`libkinematic_solver.so`），使 pybind 模块运行时能找到它们
4. 查找 `arx_a5.*.so` 和 `kinematic_solver.*.so` 并将其目录加入 `sys.path`
5. 导入 Python 包装类

## 常见问题

- **ImportError: No module named 'arx_a5'**：未运行 `cpp/build.sh` 编译 .so 文件，或编译用了错误的 Python 版本
- **OSError: libarx_r5a_src.so: cannot open shared object file**：`__init__.py` 的 ctypes 预加载未执行，通常是直接 import 子模块而非 `import arx_a5_python`
- **Python 版本不匹配**：.so 文件的 cpython 后缀必须与运行 Python 版本一致。确保用 `/usr/bin/python3` 编译

## Lint / Test

```bash
# colcon 构建验证
colcon build --packages-select arx_a5_python

# Python import 验证
/usr/bin/python3 -c "from arx_a5_python import SingleArm, BimanualArm, forward_kinematics, inverse_kinematics"
```
