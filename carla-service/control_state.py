"""Local command watchdog, independent of network and video processing."""
import math
import threading
import time


class ControlState:
    def __init__(self, timeout=0.75):
        self.timeout = timeout
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        with self.lock:
            self.latched = True
            self.command_id = -1
            self.received_at = 0
            self.values = (0.0, 1.0, 0.0)

    def accept(self, data):
        values = [data.get(key) for key in ('throttle', 'brake', 'steer')]
        command_id = data.get('commandId')
        if not isinstance(command_id, int) or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
            return False
        throttle, brake, steer = values
        if not (0 <= throttle <= 1 and 0 <= brake <= 1 and -1 <= steer <= 1):
            return False
        with self.lock:
            if command_id <= self.command_id:
                return False
            self.command_id = command_id
            now = time.monotonic()
            if now - self.received_at > self.timeout or data.get('emergency'):
                self.latched = True
            # Only a deliberate server-side resume clears a local timeout/disconnect.
            if data.get('reason') == 'Controls resumed' and not data.get('emergency'):
                self.latched = False
            self.received_at = now
            self.values = (0.0, 1.0, 0.0) if self.latched else (0.0 if brake else throttle, brake, steer)
        return True

    def stop(self):
        with self.lock:
            self.latched = True
            self.received_at = 0
            self.values = (0.0, 1.0, 0.0)

    def current(self):
        with self.lock:
            if time.monotonic() - self.received_at > self.timeout:
                self.latched = True
            return (0.0, 1.0, 0.0) if self.latched else self.values

    def is_latched(self):
        self.current()  # Apply the watchdog even before the next control-loop tick.
        with self.lock:
            return self.latched
