import threading
import time
import numpy as np
from unittest.mock import MagicMock
from a5_bimanual_arm.recorder import EpisodeRecorder


def _make_recorder():
    logger = MagicMock()
    return EpisodeRecorder(logger)


class TestRecorderThreadSafety:
    def test_concurrent_record_observation_and_image(self):
        recorder = _make_recorder()
        recorder.start_episode()
        errors = []

        def write_observations():
            try:
                for _ in range(200):
                    recorder.record_observation(
                        qpos=np.random.randn(14),
                        qvel=np.random.randn(14),
                    )
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def write_images():
            try:
                for _ in range(200):
                    recorder.record_image(
                        "images/head",
                        np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8),
                    )
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=write_observations)
        t2 = threading.Thread(target=write_images)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        recorder.stop_episode()
        assert not errors, f"Thread errors: {errors}"
        assert recorder.num_episodes == 1

    def test_stop_episode_during_recording(self):
        recorder = _make_recorder()
        recorder.start_episode()
        errors = []

        def write_images():
            try:
                for _ in range(500):
                    recorder.record_image(
                        "images/head",
                        np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8),
                    )
                    time.sleep(0.0005)
            except Exception as e:
                errors.append(e)

        def stop_and_start():
            try:
                time.sleep(0.05)
                recorder.stop_episode()
                recorder.start_episode()
                time.sleep(0.05)
                recorder.stop_episode()
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=write_images)
        t2 = threading.Thread(target=stop_and_start)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"Thread errors: {errors}"
        assert recorder.num_episodes >= 1

    def test_save_during_recording(self):
        recorder = _make_recorder()
        recorder.start_episode()
        errors = []

        def write_obs():
            try:
                for _ in range(200):
                    recorder.record_observation(
                        qpos=np.random.randn(14),
                        qvel=np.random.randn(14),
                    )
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def save():
            try:
                time.sleep(0.05)
                recorder.save("/tmp/test_recorder_thread.hdf5")
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=write_obs)
        t2 = threading.Thread(target=save)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"Thread errors: {errors}"
