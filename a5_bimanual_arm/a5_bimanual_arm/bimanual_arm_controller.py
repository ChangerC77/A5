from arx_a5_python import SingleArm
from typing import Dict, Any, List, Optional, Union
import h5py
import numpy as np
import os
import threading
import queue
import time
from pathlib import Path
from transitions import Machine

from a5_bimanual_arm.recorder import EpisodeRecorder

class BimanualArmFSM():

    states = ['initialized', 'homing', 'ready', 'collecting', 'inferring', 'replaying']

    def __init__(self, logger, mode: str = 'collect',
                 recorder_config_path: Optional[str] = None,
                 datasets_dir: str = './datasets',
                 replay_hdf5_path: str = '',
                 replay_demo_index: int = 0):
        if mode not in ('collect', 'infer', 'replay'):
            raise ValueError(f"mode must be 'collect', 'infer', or 'replay', got '{mode}'")
        self._logger = logger
        self.mode = mode
        self._homing_duration = 3.0
        self._joint_num = 14
        self._ctrl_running = True
        self._event_queue = queue.Queue()
        self._homing_start_time: Optional[float] = None
        self._save_thread: Optional[threading.Thread] = None

        self._datasets_dir = datasets_dir
        self._episode_counter = self._find_max_episode(datasets_dir) + 1
        self._replay_hdf5_path = replay_hdf5_path.strip()
        self._replay_demo_index = max(0, int(replay_demo_index))
        self._replay_actions: Optional[np.ndarray] = None
        self._replay_rel_timestamps: Optional[np.ndarray] = None
        self._replay_frame_idx = 0
        self._replay_start_time: Optional[float] = None
        self._replay_init_failed = False

        self._recorder = EpisodeRecorder(
            logger, config_path=recorder_config_path,
        )

        self.machine = Machine(
            model=self,
            states=BimanualArmFSM.states,
            initial='initialized',
            send_event=True,
        )

        self.machine.add_transition(
            trigger='start_homing', source='initialized', dest='homing',
        )
        self.machine.add_transition(
            trigger='finish_homing', source='homing', dest='ready',
        )
        self.machine.add_transition(
            trigger='begin_task', source='ready', dest='collecting',
            conditions=[lambda e: self.mode == 'collect'],
        )
        self.machine.add_transition(
            trigger='begin_task', source='ready', dest='inferring',
            conditions=[lambda e: self.mode == 'infer'],
        )
        self.machine.add_transition(
            trigger='begin_task', source='ready', dest='replaying',
            conditions=[lambda e: self.mode == 'replay'],
        )
        self.machine.add_transition(
            trigger='end_task', source=['collecting', 'inferring', 'replaying'], dest='homing',
        )

        self._ctrl_thread = threading.Thread(target=self._fsm_task, daemon=True)


        self.get_logger().info('BimanualArmFSM started.')
        self.startup_hw()

        self._ctrl_thread.start()

    # ---- state callbacks ----

    def on_enter_homing(self, event):
        self._go_home()
        self._homing_start_time = time.perf_counter()
        self.get_logger().info('Homing started, waiting %.1fs ...' % self._homing_duration)

    def on_enter_ready(self, event):
        self.get_logger().info(
            'Ready. Press SPACE to start %s, press ESC to quit.' % self.mode
        )

    def on_enter_collecting(self, event):
        self.get_logger().info('Data collection started.')
        self._init_collect()

    def on_exit_collecting(self, event):
        self.get_logger().info('Data collection stopped.')
        self._stop_collect()

    def on_enter_inferring(self, event):
        self.get_logger().info('Inference started.')
        self._init_infer()

    def on_exit_inferring(self, event):
        self.get_logger().info('Inference stopped.')

    def on_enter_replaying(self, event):
        self.get_logger().info('Replay started.')
        self._init_replay()

    def on_exit_replaying(self, event):
        self.get_logger().info('Replay stopped.')

    # ---- external key input ----

    def on_key_event(self, key: str):
        if key == 'space':
            self._event_queue.put('toggle_task')
        elif key == 'esc':
            self._event_queue.put('shutdown')

    # ---- control loop (180Hz) ----

    def _fsm_task(self):
        period = 1.0 / 30.0
        self.get_logger().info('fsm started at 30hz.')
        self.start_homing()
        while self._ctrl_running:
            t0 = time.perf_counter()
            self._process_events()
            self._process_auto_transitions()
            try:
                if self.is_ready():
                    self._gravity_compensation()
                elif self.is_collecting():
                    self._collect_step()
                elif self.is_inferring():
                    self._infer_step()
                elif self.is_replaying():
                    self._replay_step()
                # else:
                #     self._gravity_compensation()
            except Exception as e:
                self.get_logger().error(f'Control loop error: {e}')
                break
            elapsed = time.perf_counter() - t0
            sleep_time = period - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _process_events(self):
        while True:
            try:
                event = self._event_queue.get_nowait()
            except queue.Empty:
                break
            if event == 'toggle_task':
                if self.is_ready():
                    self.begin_task()
                elif self.is_collecting() or self.is_inferring() or self.is_replaying():
                    self.end_task()
            elif event == 'shutdown':
                self._ctrl_running = False

    def _process_auto_transitions(self):
        if self.is_homing() and self._homing_start_time is not None:
            if time.perf_counter() - self._homing_start_time >= self._homing_duration:
                self._homing_start_time = None
                self.finish_homing()

    # ---- placeholder methods (to be implemented) ----

    def _init_collect(self):
        if self._save_thread is not None and self._save_thread.is_alive():
            self.get_logger().info('Waiting for previous episode save to finish...')
            self._save_thread.join()
            self._save_thread = None
        self._recorder.start_episode()

    def _collect_step(self):
        self._gravity_compensation()
        qpos = self.get_joint_positions()
        qvel = self.get_joint_velocities()
        self._recorder.record_observation(qpos=qpos, qvel=qvel)
        self._recorder.record_action(qpos)

    def _stop_collect(self):
        if not self._recorder.is_recording:
            return
        self._recorder.stop_episode()
        if self._recorder.num_episodes == 0:
            return
        save_path = os.path.join(
            self._datasets_dir, f"episode_{self._episode_counter}.hdf5"
        )
        self._save_thread = threading.Thread(
            target=self._save_episode, args=(save_path,), daemon=True,
        )
        self._save_thread.start()
        self._episode_counter += 1

    def _save_episode(self, path: str):
        try:
            self._recorder.save(path)
            self._recorder.clear_episodes()
        except Exception as e:
            self.get_logger().error(f'Failed to save episode: {e}')

    def record_image(self, key: str, image):
        self._recorder.record_image(key, image)

    @staticmethod
    def _find_max_episode(datasets_dir: str) -> int:
        max_ep = -1
        if not os.path.exists(datasets_dir):
            return max_ep
        for filename in os.listdir(datasets_dir):
            if filename.startswith('episode_') and filename.endswith('.hdf5'):
                try:
                    num = int(filename.split('_')[1].split('.')[0])
                    max_ep = max(max_ep, num)
                except (ValueError, IndexError):
                    continue
        return max_ep
        

    def _init_infer(self):
        pass

    def _infer_step(self):
        pass

    @staticmethod
    def _find_latest_episode_file(datasets_dir: str) -> Optional[Path]:
        datasets_path = Path(datasets_dir)
        if not datasets_path.exists():
            return None
        best_num = -1
        best_path: Optional[Path] = None
        for path in datasets_path.glob('episode_*.hdf5'):
            stem = path.stem
            try:
                num = int(stem.split('_', 1)[1])
            except (IndexError, ValueError):
                continue
            if num > best_num:
                best_num = num
                best_path = path
        return best_path

    def _resolve_replay_file(self) -> Optional[Path]:
        if self._replay_hdf5_path:
            path = Path(self._replay_hdf5_path).expanduser()
            if not path.is_absolute():
                path = Path.cwd() / path
            return path
        return self._find_latest_episode_file(self._datasets_dir)

    def _load_replay_episode(self, episode_path: Path, demo_idx: int) -> Dict[str, np.ndarray]:
        if not episode_path.exists():
            raise FileNotFoundError(f'Replay file not found: {episode_path}')

        with h5py.File(str(episode_path), 'r') as h5_file:
            if 'data' not in h5_file:
                raise KeyError(f"Missing 'data' group in {episode_path}")

            data_group = h5_file['data']
            demo_key = f'demo_{demo_idx}'
            if demo_key not in data_group:
                raise KeyError(f"Missing '{demo_key}' in {episode_path}")
            demo_group = data_group[demo_key]

            if 'actions' in demo_group:
                actions = np.asarray(demo_group['actions'], dtype=np.float64)
            elif 'observations' in demo_group and 'qpos' in demo_group['observations']:
                actions = np.asarray(demo_group['observations']['qpos'], dtype=np.float64)
            else:
                raise KeyError('Replay episode must contain data/demo_x/actions or data/demo_x/observations/qpos')

            if actions.ndim != 2 or actions.shape[1] != self._joint_num:
                raise ValueError(
                    f'Invalid replay action shape {actions.shape}, expected (N, {self._joint_num})'
                )

            if 'timestamp' in demo_group:
                timestamps = np.asarray(demo_group['timestamp'], dtype=np.float64)
            else:
                self.get_logger().warning('Replay episode has no timestamp, fallback to 30Hz timing.')
                timestamps = np.arange(actions.shape[0], dtype=np.float64) / 30.0

        frame_count = min(actions.shape[0], timestamps.shape[0])
        if frame_count <= 0:
            raise ValueError('Replay episode is empty')

        actions = actions[:frame_count]
        timestamps = timestamps[:frame_count]
        if frame_count > 1:
            delta = np.diff(timestamps)
            if np.any(delta < 0.0):
                self.get_logger().warning('Replay timestamps are out of order, fallback to 30Hz timing.')
                rel_timestamps = np.arange(frame_count, dtype=np.float64) / 30.0
            else:
                rel_timestamps = timestamps - timestamps[0]
        else:
            rel_timestamps = np.zeros((1,), dtype=np.float64)

        return {
            'actions': actions,
            'rel_timestamps': rel_timestamps,
        }

    def _init_replay(self):
        self._replay_actions = None
        self._replay_rel_timestamps = None
        self._replay_frame_idx = 0
        self._replay_start_time = None
        self._replay_init_failed = False

        replay_path = self._resolve_replay_file()
        if replay_path is None:
            self.get_logger().error(
                f'No replay file found under datasets_dir={self._datasets_dir}. '
                'Expected files like episode_0.hdf5.'
            )
            self._replay_init_failed = True
            return

        try:
            replay_data = self._load_replay_episode(replay_path, self._replay_demo_index)
        except Exception as e:
            self.get_logger().error(f'Failed to load replay episode: {e}')
            self._replay_init_failed = True
            return

        self._replay_actions = replay_data['actions']
        self._replay_rel_timestamps = replay_data['rel_timestamps']
        self._replay_frame_idx = 0
        self._replay_start_time = time.perf_counter()
        self.get_logger().info(
            f"Replay loaded: file={replay_path}, demo={self._replay_demo_index}, "
            f"frames={self._replay_actions.shape[0]}"
        )

    def _replay_step(self):
        if self._replay_init_failed:
            self.end_task()
            return

        if self._replay_actions is None or self._replay_rel_timestamps is None or self._replay_start_time is None:
            self.get_logger().error('Replay is not initialized correctly.')
            self.end_task()
            return

        total_frames = self._replay_actions.shape[0]
        if self._replay_frame_idx >= total_frames:
            self.get_logger().info('Replay finished.')
            self.end_task()
            return

        elapsed = time.perf_counter() - self._replay_start_time
        next_idx = self._replay_frame_idx
        while next_idx < total_frames and self._replay_rel_timestamps[next_idx] <= elapsed:
            next_idx += 1

        if next_idx == self._replay_frame_idx:
            return

        send_idx = next_idx - 1
        action = self._replay_actions[send_idx]
        half = self._joint_num // 2
        self.left_arm.set_joint_positions(action[:half])
        self.right_arm.set_joint_positions(action[half:])
        self._replay_frame_idx = next_idx

        if self._replay_frame_idx >= total_frames:
            self.get_logger().info('Replay completed all frames.')
            self.end_task()

    # ---- hardware methods ----

    def _go_home(self) -> Dict[str, bool]:
        return {"left": self.left_arm.go_home(), "right": self.right_arm.go_home()}

    def _gravity_compensation(self) -> Dict[str, bool]:
        return {
            "left": self.left_arm.gravity_compensation(),
            "right": self.right_arm.gravity_compensation(),
        }

    def _set_joint_positions(
        self,
        positions: Dict[str, Union[float, List[float], np.ndarray]],
        joint_names: Optional[Dict[str, Union[str, List[str]]]] = None,
        **kwargs
    ):
        if "left" in positions:
            self.left_arm.set_joint_positions(
                positions["left"],
                joint_names.get("left") if joint_names else None,
                **kwargs
            )
        if "right" in positions:
            self.right_arm.set_joint_positions(
                positions["right"],
                joint_names.get("right") if joint_names else None,
                **kwargs
            )

    def get_joint_positions(
        self,
    ) -> np.ndarray:
        half = self._joint_num // 2
        result = np.zeros(self._joint_num)
        left = self.left_arm.get_joint_positions()
        right = self.right_arm.get_joint_positions()
        result[:half] = left[:half]
        result[half:] = right[:half]
        return result

    def get_joint_velocities(
        self,
    ) -> np.ndarray:
        half = self._joint_num // 2
        result = np.zeros(self._joint_num)
        left = self.left_arm.get_joint_velocities()
        right = self.right_arm.get_joint_velocities()
        result[:half] = left[:half]
        result[half:] = right[:half]
        return result

    def get_logger(self):
        return self._logger

    def startup_hw(self):
        arm_config_0: Dict[str, Any] = {
            "can_port": "can1",
            "urdf_name": "a5.urdf",
        }
        arm_config_1: Dict[str, Any] = {
            "can_port": "can3",
            "urdf_name": "a5.urdf",
        }
        self.left_arm = SingleArm(arm_config_0)
        self.right_arm = SingleArm(arm_config_1)

    def shutdown(self):
        if self._recorder.is_recording:
            self._recorder.stop_episode()
        self._ctrl_running = False
        self._ctrl_thread.join(timeout=2.0)
        if self._save_thread is not None and self._save_thread.is_alive():
            self._save_thread.join(timeout=5.0)
            self._save_thread = None
        self.get_logger().info('BimanualArmFSM shut down.')
