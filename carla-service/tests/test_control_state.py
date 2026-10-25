import sys
import time
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from control_state import ControlState


class ControlStateTest(unittest.TestCase):
    def test_timeout_and_reordered_command(self):
        controls = ControlState(timeout=0.02)
        self.assertEqual(controls.current(), (0.0, 1.0, 0.0))
        controls.accept(dict(commandId=0, throttle=0, brake=1, steer=0, reason='Controls resumed'))
        self.assertTrue(controls.accept(dict(commandId=2, throttle=1, brake=0, steer=0.5)))
        self.assertFalse(controls.accept(dict(commandId=1, throttle=0, brake=0, steer=0)))
        self.assertEqual(controls.current(), (1, 0, 0.5))
        time.sleep(0.03)
        self.assertEqual(controls.current(), (0.0, 1.0, 0.0))

    def test_timeout_requires_explicit_resume(self):
        controls = ControlState(timeout=0.02)
        controls.accept(dict(commandId=0, throttle=0, brake=1, steer=0, reason='Controls resumed'))
        time.sleep(0.03)
        controls.accept(dict(commandId=1, throttle=1, brake=0, steer=0))
        self.assertEqual(controls.current(), (0.0, 1.0, 0.0))
        controls.accept(dict(commandId=2, throttle=0, brake=1, steer=0, reason='Controls resumed'))
        controls.accept(dict(commandId=3, throttle=1, brake=0, steer=0))
        self.assertEqual(controls.current(), (1, 0, 0))
        controls.stop()
        controls.accept(dict(commandId=4, throttle=1, brake=0, steer=0))
        self.assertEqual(controls.current(), (0.0, 1.0, 0.0))

    def test_emergency_and_invalid_values(self):
        controls = ControlState()
        self.assertTrue(controls.accept(dict(commandId=1, throttle=1, brake=0, steer=1, emergency=True)))
        self.assertEqual(controls.current(), (0.0, 1.0, 0.0))
        self.assertFalse(controls.accept(dict(commandId=2, throttle=float('nan'), brake=0, steer=0)))
        self.assertFalse(controls.accept(dict(commandId=3, throttle=2, brake=0, steer=0)))
        controls.reset()
        self.assertTrue(controls.accept(dict(commandId=1, throttle=1, brake=1, steer=0)))
        self.assertEqual(controls.current(), (0.0, 1, 0))


if __name__ == '__main__':
    unittest.main()
