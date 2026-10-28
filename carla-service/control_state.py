"""Local command watchdog, independent of network and video processing."""
import math
import threading
import time


class ControlState:
    def __init__(self, timeout=0.75):
        self.timeout = timeout
        self.lock = threading.RLock()
        self.reset()

    def reset(self):
        with self.lock:
            self.latched = True
            self.command_id = -1
            self.received_at = 0
            self.values = (0.0, 1.0, 0.0)
            self.mode = 'STOPPED'
            self.reverse = False
            self.supervised_at = 0
            self.generation = getattr(self, 'generation', 0) + 1
            self.reason = 'Initial stop'

    def accept(self, data):
        values = [data.get(key) for key in ('throttle', 'brake', 'steer')]
        command_id = data.get('commandId')
        if type(command_id) is not int or any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            return False
        throttle, brake, steer = values
        if not (0 <= throttle <= 1 and 0 <= brake <= 1 and -1 <= steer <= 1):
            return False
        with self.lock:
            if command_id <= self.command_id:
                return False
            self.command_id = command_id
            now = time.monotonic()
            if data.get('emergency'):
                self.latched = True
                self.generation += 1
                if data.get('reason') == 'Emergency stop':
                    self.mode = 'EMERGENCY_STOP'
                elif self.mode != 'TAKEOVER_REQUESTED':
                    self.mode = 'STOPPED'
                self.reason = data.get('reason', 'Safety stop')
            elif self.mode == 'AUTONOMOUS':
                # Manual key packets must never become autonomous actuator input.
                return False
            elif now - self.received_at > self.timeout:
                self.latched = True
            # Only a deliberate server-side resume clears a local timeout/disconnect.
            if data.get('reason') == 'Controls resumed' and not data.get('emergency'):
                self.latched = False
                self.mode = 'MANUAL'
                self.reason = 'Controls resumed'
            self.received_at = now
            self.values = (0.0, 1.0, 0.0) if self.latched else (0.0 if brake else throttle, brake, steer)
        return True

    def stop(self, reason='Safety stop', mode='STOPPED'):
        with self.lock:
            self.latched = True
            self.generation += 1
            self.reason = reason
            self.mode = mode
            self.received_at = 0
            self.values = (0.0, 1.0, 0.0)

    def current(self):
        with self.lock:
            last = self.supervised_at if self.mode == 'AUTONOMOUS' else self.received_at
            if not self.latched and time.monotonic() - last > self.timeout:
                self.stop('Supervision timeout' if self.mode == 'AUTONOMOUS' else 'Control timeout')
            return (0.0, 1.0, 0.0) if self.latched else self.values

    def supervise(self):
        with self.lock:
            self.supervised_at = time.monotonic()

    def begin_operation(self, command_id, expected_generation=None):
        with self.lock:
            if expected_generation is not None and expected_generation != self.generation:
                raise ValueError('Queued operation cancelled by a newer safety stop')
            if type(command_id) is not int or command_id <= self.command_id:
                raise ValueError('Stale research command; reconnect and try again')
            self.command_id = command_id
            return self.generation

    def transition(self, mode, generation):
        with self.lock:
            if generation != self.generation:
                raise ValueError('Operation cancelled by a newer safety stop')
            if mode == 'AUTONOMOUS' and time.monotonic() - self.supervised_at > self.timeout:
                raise ValueError('Fresh received-video supervision is required')
            self.mode = mode
            self.latched = mode not in ('MANUAL', 'AUTONOMOUS')
            self.received_at = time.monotonic()
            self.values = (0.0, 1.0, 0.0)
            self.reason = 'Operator selected ' + mode

    def snapshot(self):
        with self.lock:
            self.current()
            return {'mode': self.mode, 'direction': 'reverse' if self.reverse else 'forward',
                    'stopped': self.latched, 'reason': self.reason, 'generation': self.generation,
                    'commandId': self.command_id}

    def is_latched(self):
        self.current()  # Apply the watchdog even before the next control-loop tick.
        with self.lock:
            return self.latched
