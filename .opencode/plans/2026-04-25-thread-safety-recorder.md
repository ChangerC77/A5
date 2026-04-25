# EpisodeRecorder 线程安全修复计划

> **给Claude:** 必需子技能:使用superpowers:executing-plans来逐任务实现此计划。

**目标:** 为 `EpisodeRecorder` 添加 `threading.RLock` 保护所有共享状态的并发访问。

**架构:** 在 `EpisodeRecorder` 中添加一把 RLock，所有公共方法（`start_episode`、`stop_episode`、`record_observation`、`record_action`、`record_image`、`save`、`clear_episodes`）用 `with self._lock:` 保护共享状态。图像转换（CPU 密集）在锁外完成以降低竞争。使用 RLock 而非 Lock 是因为 `save` 内部会调用 `stop_episode`。

**技术栈:** Python `threading.RLock`、现有测试框架 pytest

---

### 任务 1: 添加 RLock 并保护公共方法

**文件:**
- 修改: `a5_bimanual_arm/a5_bimanual_arm/recorder.py`

**步骤 1: 在 `__init__` 中添加 RLock**

在文件顶部 `import` 区域添加：

```python
import threading
```

在 `__init__` 方法中（第 95 行 `self._current_episode` 之前）添加：

```python
self._lock = threading.RLock()
```

**步骤 2: 为 `start_episode` 加锁**

将整个方法体包裹在 `with self._lock:` 中（方法体内代码不变）。

**步骤 3: 为 `record_observation` 加锁**

将方法体包裹在 `with self._lock:` 中。

**步骤 4: 为 `record_action` 加锁**

将方法体包裹在 `with self._lock:` 中。

**步骤 5: 为 `record_image` 加锁（图像转换在锁外）**

关键改动：将 `_ros_image_to_rgb()` / numpy 转换移到 `with self._lock:` 之前，锁内仅做 deque/dict 写入和 `_try_sync_frame` 调用。`key not in self._image_key_names` 检查也可留在锁外，因为 `_image_key_names` 在 `__init__` 后不可变。

```python
def record_image(self, key: str, image: Union[RosImage, np.ndarray]) -> None:
    if key not in self._image_key_names:
        self._logger.warning(f'Unknown image key: {key}')
        return
    if isinstance(image, RosImage):
        rgb = _ros_image_to_rgb(image)
    else:
        if image.ndim == 2:
            rgb = np.stack([image, image, image], axis=-1)
        elif image.shape[2] == 4:
            rgb = image[:, :, :3]
        else:
            rgb = image
        rgb = np.asarray(rgb, dtype=np.uint8).copy()
    with self._lock:
        if not self._recording:
            return
        t = time.perf_counter()
        self._image_ts[key].append(t)
        self._image_data[key].append(rgb)
        self._latest_image_time[key] = t
        if len(self._latest_image_time) == len(self._image_key_names):
            self._try_sync_frame()
```

**步骤 6: 为 `stop_episode` 加锁**

将方法体包裹在 `with self._lock:` 中。

**步骤 7: 为 `save` 加锁（HDF5 写入在锁外）**

在锁内完成 `stop_episode()` 调用和 episodes 引用拷贝，在锁外写 HDF5：

```python
def save(self, output_path: str) -> None:
    with self._lock:
        if self._recording:
            self.stop_episode()
        episodes = list(self._episodes)
        config = self._config

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    self._logger.info(f'Saving {len(episodes)} episodes to {output_path}')

    with h5py.File(str(output_path), "w") as f:
        # ... 原有 HDF5 写入逻辑，改用局部变量 episodes/config
```

**步骤 8: 为 `clear_episodes` 加锁**

将方法体包裹在 `with self._lock:` 中。

**步骤 9: 提交**

```bash
git add a5_bimanual_arm/a5_bimanual_arm/recorder.py
git commit -m "fix: add RLock to EpisodeRecorder for thread safety"
```

---

### 任务 2: 编写并发测试

**文件:**
- 创建: `a5_bimanual_arm/test/test_recorder_thread_safety.py`

**步骤 1: 编写三个并发测试用例**

1. `test_concurrent_record_observation_and_image` — 两个线程分别调用 `record_observation` 和 `record_image`，验证无异常且 episode 完整
2. `test_stop_episode_during_recording` — 一个线程写图像，另一个线程 stop+start+stop，验证无异常
3. `test_save_during_recording` — 一个线程写观测，另一个线程调用 `save`，验证无异常

**步骤 2: 运行测试**

```bash
cd /home/tk/projects/A5
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python -m pytest a5_bimanual_arm/test/test_recorder_thread_safety.py -v
```

**步骤 3: 提交**

```bash
git add a5_bimanual_arm/test/test_recorder_thread_safety.py
git commit -m "test: add thread safety tests for EpisodeRecorder"
```

---

### 任务 3: 构建验证

**步骤 1: 构建**

```bash
source /opt/ros/jazzy/setup.bash && cd /home/tk/projects/A5 && colcon build --packages-select a5_bimanual_arm
```

**步骤 2: 运行全量测试 + lint**

```bash
source /opt/ros/jazzy/setup.bash && source install/setup.bash && python -m pytest a5_bimanual_arm/test/ -v
python -m flake8 a5_bimanual_arm/a5_bimanual_arm/recorder.py a5_bimanual_arm/test/test_recorder_thread_safety.py
```

**步骤 3: 提交（如有 lint 修复）**
