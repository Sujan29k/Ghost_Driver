"""Debounced prototype policy. Sources are explicit; no learned hazard claims."""
import time

DEFAULT_POLICY = {'stallSeconds': 12.0, 'deviationMeters': 5.0,
                  'deviationSeconds': 2.0, 'weatherThreshold': 80.0,
                  'hazardDistance': 12.0, 'blockedSeconds': 2.0}


class TakeoverPolicy:
    def __init__(self, **settings):
        self.configure(settings)
        self.reset()

    def configure(self, settings):
        bounds = {'stallSeconds': (3, 120), 'deviationMeters': (1, 30), 'deviationSeconds': (.5, 30),
                  'weatherThreshold': (1, 100), 'hazardDistance': (3, 50), 'blockedSeconds': (.5, 30)}
        for key, value in settings.items():
            if key not in bounds or type(value) not in (int, float) or not bounds[key][0] <= value <= bounds[key][1]:
                raise ValueError('Invalid takeover threshold: ' + key)
        self.settings = {**getattr(self, 'settings', DEFAULT_POLICY), **settings}

    def reset(self):
        self.since = {}
        self.last_progress = None
        self.progress_at = None

    def _held(self, key, condition, seconds, now):
        if not condition:
            self.since.pop(key, None)
            return False
        self.since.setdefault(key, now)
        return now - self.since[key] >= seconds

    def evaluate(self, *, progress, speed, at_red_light=False, deviation=0, hazard_distance=None,
                 weather=0, collision=False, sensor_fault=False, blocked=False, now=None):
        now = time.monotonic() if now is None else now
        if collision:
            return {'reason': 'Collision sensor event', 'source': 'sensor'}
        if sensor_fault:
            return {'reason': 'Required safety sensor unavailable', 'source': 'sensor'}
        if self._held('weather', weather >= self.settings['weatherThreshold'], 1, now):
            return {'reason': 'Configured severe-weather threshold', 'source': 'scripted'}
        if hazard_distance is not None and hazard_distance <= self.settings['hazardDistance']:
            return {'reason': 'Approaching scripted hazard zone', 'source': 'scripted'}
        if self._held('deviation', deviation > self.settings['deviationMeters'], self.settings['deviationSeconds'], now):
            return {'reason': 'Route deviation', 'source': 'simulator-state'}
        if self._held('blocked', blocked and not at_red_light, self.settings['blockedSeconds'], now):
            return {'reason': 'Persistent obstacle sensor blockage', 'source': 'sensor'}
        if at_red_light or self.last_progress is None or progress > self.last_progress + 1:
            self.last_progress, self.progress_at = progress, now
        if speed < 1 and now - self.progress_at >= self.settings['stallSeconds']:
            return {'reason': 'Persistent lack of route progress', 'source': 'simulator-state'}
        return None
