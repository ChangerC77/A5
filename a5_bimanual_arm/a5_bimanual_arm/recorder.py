import json
import threading
import time
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Union

import cv_bridge
import h5py
import numpy as np
from sensor_msgs.msg import CompressedImage as RosImage


_DEFAULT_CONFIG = {
    "obs_keys": [
        {"name": "qpos", "type": "float", "shape": [14]},
        {"name": "qvel", "type": "float", "shape": [14]},
        {"name": "images/head", "type": "image"},
        {"name": "images/left_wrist", "type": "image"},
        {"name": "images/right_wrist", "type": "image"},
    ],
    "action_key": [ {"name": "actions", "type": "float", "shape": [14]},
                    {"name": "actions_eef", "type": "float", "shape": [14]}],
}

_CV_BRIDGE = cv_bridge.CvBridge()

_BGRA_TO_RGB = np.array([2, 1, 0], dtype=np.intp)


def _ros_image_to_rgb(msg: RosImage) -> np.ndarray:
    return _CV_BRIDGE.compressed_imgmsg_to_cv2(msg, desired_encoding="rgb8")


class EpisodeRecorder:
    def __init__(
        self,
        logger,
        config_path: Optional[str] = None,
        img_sync_tolerance: float = 0.005,
        joint_buffer_maxlen: int = 2000,
    ):
        self._logger = logger
        if config_path is not None:
            with open(config_path, "r") as f:
                self._config = json.load(f)
            self._logger.info(f'Loaded config from {config_path}')
        else:
            self._config = _DEFAULT_CONFIG
            self._logger.info('Using default config')

        self._img_sync_tolerance = img_sync_tolerance
        self._joint_buffer_maxlen = joint_buffer_maxlen

        self._obs_keys = self._config["obs_keys"]
        self._action_keys = self._config.get("action_key", None)
        if self._action_keys is None:
            self._action_keys = []
        elif isinstance(self._action_keys, dict):
            self._action_keys = [self._action_keys]

        self._float_obs_keys = [k for k in self._obs_keys if k["type"] == "float"]
        self._image_obs_keys = [k for k in self._obs_keys if k["type"] == "image"]

        self._image_key_names = [k["name"] for k in self._image_obs_keys]
        self._float_key_names = [k["name"] for k in self._float_obs_keys]

        self._episodes: List[Dict[str, List[np.ndarray]]] = []
        self._recording = False

        self._joint_ts: deque = deque(maxlen=joint_buffer_maxlen)
        self._joint_data: Dict[str, deque] = {}
        self._action_ts: deque = deque(maxlen=joint_buffer_maxlen)
        self._action_data: Dict[str, deque] = {}
        self._image_ts: Dict[str, deque] = {}
        self._image_data: Dict[str, deque] = {}
        self._latest_image_time: Dict[str, float] = {}
        self._sync_attempts = 0
        self._sync_successes = 0

        self._lock = threading.RLock()
        self._current_episode: Dict[str, List[np.ndarray]] = {}

    def start_episode(self) -> None:
        with self._lock:
            if self._recording:
                self.stop_episode()

            self._recording = True
            self._logger.info(f'Episode {len(self._episodes)} started')
            self._joint_data = {name: deque(maxlen=self._joint_buffer_maxlen) for name in self._float_key_names}
            self._action_ts.clear()
            self._action_data.clear()
            self._image_ts = {name: deque(maxlen=500) for name in self._image_key_names}
            self._image_data = {name: deque(maxlen=500) for name in self._image_key_names}
            self._latest_image_time = {}
            self._sync_attempts = 0
            self._sync_successes = 0

            self._current_episode = {}
            self._current_episode["timestamp"] = []
            for k in self._float_key_names:
                self._current_episode[f"observations/{k}"] = []
            for k in self._image_key_names:
                self._current_episode[f"observations/{k}"] = []
            for action_key in self._action_keys:
                self._current_episode[action_key["name"]] = []

    def record_observation(self, **kwargs: np.ndarray) -> None:
        with self._lock:
            if not self._recording:
                return
            for name in self._float_key_names:
                if name not in kwargs:
                    self._logger.warning(f'Missing float obs key: {name}')
                    continue
                t = time.perf_counter()
                self._joint_ts.append(t)
                self._joint_data[name].append(np.asarray(kwargs[name], dtype=np.float64).copy())

    def record_action(self, **kwargs: np.ndarray) -> None:
        with self._lock:
            if not self._recording or not self._action_keys:
                return
            if not self._action_data:
                self._action_data = {k["name"]: deque(maxlen=self._joint_buffer_maxlen) for k in self._action_keys}
            t = time.perf_counter()
            for action_key in self._action_keys:
                name = action_key["name"]
                if name not in kwargs:
                    self._logger.warning(f'Missing action key: {name}')
                    continue
                self._action_ts.append(t)
                self._action_data[name].append(np.asarray(kwargs[name], dtype=np.float64).copy())

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

            self._logger.debug(
                f"Image received key={key}, ts={t:.6f}, "
                f"latest_keys={list(self._latest_image_time.keys())}"
            )

            if len(self._latest_image_time) == len(self._image_key_names):
                self._try_sync_frame()

    def _try_sync_frame(self) -> None:
        self._sync_attempts += 1
        times = list(self._latest_image_time.values())
        t_max = max(times)
        t_min = min(times)
        skew = t_max - t_min
        self._logger.debug(
            f"Sync attempt #{self._sync_attempts}: skew={skew:.6f}s, "
            f"tolerance={self._img_sync_tolerance:.6f}s"
        )
        if skew > self._img_sync_tolerance:
            self._logger.debug(
                f"Sync rejected: image skew too large ({skew:.6f}s > {self._img_sync_tolerance:.6f}s)"
            )
            return

        if len(self._joint_ts) < 2:
            self._logger.debug(
                f"Sync rejected: insufficient joint samples (len={len(self._joint_ts)})"
            )
            return

        t_ref = t_max
        self._current_episode["timestamp"].append(np.float64(t_ref))

        frame_ok = True
        for key_name in self._float_key_names:
            interpolated = self._interpolate_joint(t_ref, self._joint_ts, self._joint_data[key_name])
            if interpolated is None:
                self._logger.debug(
                    f"Sync rejected: interpolation failed for {key_name}, "
                    f"joint_ts_len={len(self._joint_ts)}, key_buffer_len={len(self._joint_data[key_name])}"
                )
                frame_ok = False
                break
            self._current_episode[f"observations/{key_name}"].append(interpolated)

        if frame_ok:
            for key_name in self._image_key_names:
                if len(self._image_data[key_name]) == 0:
                    self._logger.debug(f"Sync rejected: empty image buffer for {key_name}")
                    frame_ok = False
                    break
                self._current_episode[f"observations/{key_name}"].append(self._image_data[key_name][-1])

        if not frame_ok:
            self._current_episode["timestamp"].pop()
            for key_name in self._float_key_names:
                if len(self._current_episode[f"observations/{key_name}"]) > len(self._current_episode["timestamp"]):
                    self._current_episode[f"observations/{key_name}"].pop()
            return

        if self._action_keys:
            for action_key in self._action_keys:
                name = action_key["name"]
                if name not in self._action_data or len(self._action_data[name]) == 0:
                    continue
                if len(self._action_data[name]) >= 2:
                    interpolated = self._interpolate_joint(t_ref, self._action_ts, self._action_data[name])
                    if interpolated is not None:
                        self._current_episode[name].append(interpolated)
                elif len(self._action_data[name]) == 1:
                    self._current_episode[name].append(self._action_data[name][0].copy())

        self._sync_successes += 1
        self._logger.info(f"episode_frames={len(self._current_episode['timestamp'])}")
        self._logger.debug(
            f"Sync success #{self._sync_successes}: t_ref={t_ref:.6f}, "
            f"action_samples={len(self._action_ts)}, joint_samples={len(self._joint_ts)}"
        )

        self._latest_image_time.clear()

    @staticmethod
    def _interpolate_joint(
        t_ref: float,
        ts: deque,
        data: deque,
    ) -> Optional[np.ndarray]:
        if len(ts) < 2:
            if len(ts) == 1:
                return np.asarray(data[0], dtype=np.float64).copy()
            return None

        ts_arr = np.array(ts)
        idx = np.searchsorted(ts_arr, t_ref)

        if idx == 0:
            return np.asarray(data[0], dtype=np.float64).copy()
        if idx >= len(ts_arr):
            return np.asarray(data[-1], dtype=np.float64).copy()

        t0, t1 = ts_arr[idx - 1], ts_arr[idx]
        d0 = np.asarray(data[idx - 1], dtype=np.float64)
        d1 = np.asarray(data[idx], dtype=np.float64)
        alpha = (t_ref - t0) / (t1 - t0) if t1 != t0 else 0.0
        return d0 + alpha * (d1 - d0)

    def stop_episode(self) -> None:
        with self._lock:
            if not self._recording:
                return
            self._recording = False

            per_key_counts = {k: len(v) for k, v in self._current_episode.items()}
            self._logger.info(
                f"Stopping episode with counts={per_key_counts}, "
                f"sync_attempts={self._sync_attempts}, sync_successes={self._sync_successes}"
            )

            has_data = any(len(v) > 0 for v in self._current_episode.values())
            if has_data:
                self._episodes.append(self._current_episode)
                frame_count = len(self._current_episode.get("timestamp", []))
                self._logger.info(f'Episode {len(self._episodes) - 1} stopped, {frame_count} frames recorded')
            else:
                self._logger.warning('Episode stopped with no data')
            self._current_episode = {}

    def clear_episodes(self) -> None:
        with self._lock:
            self._episodes.clear()

    @property
    def num_episodes(self) -> int:
        return len(self._episodes)

    @property
    def is_recording(self) -> bool:
        return self._recording

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
            data_group = f.create_group("data")
            for i, episode in enumerate(episodes):
                demo_group = data_group.create_group(f"demo_{i}")
                obs_group = demo_group.create_group("observations")

                for key, values in episode.items():
                    if not values:
                        continue
                    if key == "timestamp":
                        arr = np.array(values, dtype=np.float64)
                        demo_group.create_dataset("timestamp", data=arr)
                        continue
                    arr = np.stack(values, axis=0)
                    parts = key.split("/")
                    if parts[0] == "observations" and len(parts) > 2:
                        if parts[1] not in obs_group:
                            img_group = obs_group.create_group(parts[1])
                        else:
                            img_group = obs_group[parts[1]]
                        img_group.create_dataset(parts[2], data=arr, compression="gzip", compression_opts=4)
                    elif parts[0] == "observations" and len(parts) == 2:
                        obs_group.create_dataset(parts[1], data=arr)
                    else:
                        demo_group.create_dataset(key, data=arr)

            meta_group = f.create_group("meta")
            meta_group.create_dataset("config", data=json.dumps(config))
            meta_group.create_dataset("num_episodes", data=len(episodes))
        self._logger.info(f'Saved {len(episodes)} episodes to {output_path}')

    def get_logger(self):
        return self._logger

    @classmethod
    def load_config_template(cls, output_path: str) -> None:
        with open(output_path, "w") as f:
            json.dump(_DEFAULT_CONFIG, f, indent=2)
