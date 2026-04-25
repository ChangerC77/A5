import os
import select
import sys
import termios
import threading
import time
import tty

try:
    from pynput import keyboard as pynput_keyboard
except ImportError:
    pynput_keyboard = None


class KeyboardHandler:
    KEY_STATE_PRESSED = "pressed"

    def __init__(self):
        self._callbacks = {}
        self._running = False
        self._thread = None
        self._listener = None

    def add_key_callback(self, key, callback):
        self._callbacks.setdefault(key, []).append(callback)

    def start(self):
        if self._running:
            return
        self._running = True
        if pynput_keyboard is not None:
            self._listener = pynput_keyboard.Listener(on_press=self._on_press)
            self._listener.start()
            return

        self._thread = threading.Thread(target=self._listen_loop_stdin, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _emit(self, key):
        for callback in self._callbacks.get(key, []):
            callback(key, self.KEY_STATE_PRESSED)

    def _on_press(self, key):
        if not self._running:
            return False
        if key == pynput_keyboard.Key.space:
            self._emit("space")
        elif key == pynput_keyboard.Key.esc:
            self._emit("esc")

    def _listen_loop_stdin(self):
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
