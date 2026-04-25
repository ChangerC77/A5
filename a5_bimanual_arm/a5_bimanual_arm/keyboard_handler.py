import os
import select
import sys
import termios
import threading
import time
import tty


class KeyboardHandler:
    KEY_STATE_PRESSED = "pressed"

    def __init__(self):
        self._callbacks = {}
        self._running = False
        self._thread = None

    def add_key_callback(self, key, callback):
        self._callbacks.setdefault(key, []).append(callback)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _emit(self, key):
        for callback in self._callbacks.get(key, []):
            callback(key, self.KEY_STATE_PRESSED)

    def _listen_loop(self):
        if not sys.stdin.isatty():
            while self._running:
                time.sleep(0.1)
            return

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while self._running:
                ready, _, _ = select.select([fd], [], [], 0.1)
                if not ready:
                    continue
                ch = os.read(fd, 1)
                if not ch:
                    continue
                if ch == b" ":
                    self._emit("space")
                elif ch == b"\x1b":
                    self._emit("esc")
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
