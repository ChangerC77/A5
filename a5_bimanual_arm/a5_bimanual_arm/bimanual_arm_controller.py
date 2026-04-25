from arx_a5_python import SingleArm
from typing import Dict, Any, List, Optional, Union
import numpy as np
import threading
import queue
import time
from transitions import Machine

class BimanualArmFSM():

    states = ['initialized', 'homing', 'ready', 'collecting', 'inferring']

    def __init__(self, logger, mode: str = 'collect',ctrl_rate=180):
        if mode not in ('collect', 'infer'):
            raise ValueError(f"mode must be 'collect' or 'infer', got '{mode}'")
        self._logger = logger
        self._ctrl_rate=ctrl_rate
        self.mode = mode
        self._homing_duration = 3.0
        self._joint_num = 14
        self._ctrl_running = True
        self._event_queue = queue.Queue()
        self._homing_start_time: Optional[float] = None

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
            trigger='end_task', source=['collecting', 'inferring'], dest='homing',
        )

        self._ctrl_thread = threading.Thread(target=self._control_loop, daemon=True)


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

    def on_enter_inferring(self, event):
        self.get_logger().info('Inference started.')
        self._init_infer()

    def on_exit_inferring(self, event):
        self.get_logger().info('Inference stopped.')

    # ---- external key input ----

    def on_key_event(self, key: str):
        if key == 'space':
            self._event_queue.put('toggle_task')
        elif key == 'esc':
            self._event_queue.put('shutdown')

    # ---- control loop (180Hz) ----

    def _control_loop(self):
        period = 1.0 / self._ctrl_rate
        self.get_logger().info('Control loop started at 180Hz.')
        self.start_homing()
        while self._ctrl_running:
            t0 = time.perf_counter()
            self._process_events()
            self._process_auto_transitions()
            try:
                if self.is_collecting():
                    self._collect_step()
                elif self.is_inferring():
                    self._infer_step()
                else:
                    self._gravity_compensation()
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
                elif self.is_collecting() or self.is_inferring():
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
        pass

    def _collect_step(self):
        pass
        

    def _init_infer(self):
        pass

    def _infer_step(self):
        pass

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
        result = np.zeros(self._joint_num)
        for idx in range(self._joint_num):
            result[idx] = self.left_arm.get_joint_positions()[idx]
            result[idx+self._joint_num/2] = self.right_arm.get_joint_positions()[idx]
        return result

    def get_joint_velocities(
        self,
    ) -> np.ndarray:
        result = np.zeros(self._joint_num)
        for idx in range(self._joint_num):
            result[idx] = self.left_arm.get_joint_velocities()[idx]
            result[idx+self._joint_num/2] = self.right_arm.get_joint_velocities()[idx]
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
        self._ctrl_running = False
        self._ctrl_thread.join(timeout=2.0)
        self.get_logger().info('BimanualArmFSM shut down.')
