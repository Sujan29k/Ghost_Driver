import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
AVAILABLE = all(importlib.util.find_spec(name) for name in ('numpy', 'cv2'))


@unittest.skipUnless(AVAILABLE, 'Install requirements-ai.txt for image processing tests')
class PerceptionTest(unittest.TestCase):
    def test_road_class_filter_advisory_and_motion_shape(self):
        import cv2
        import numpy as np
        from perception import Perception
        # Model output fixture isolates class filtering and advisory semantics.
        detections = [[0, 0, 50, 50, .9, 0], [1, 1, 5, 5, .8, 1]]
        result = NS(names={0: 'car', 1: 'chair'},
                    boxes=NS(data=NS(cpu=lambda: NS(tolist=lambda: detections))))
        p = Perception.__new__(Perception)
        p.cv2, p.np = cv2, np
        p.model = NS(predict=lambda *args, **kwargs: [result])
        p.device, p.confidence, p.flow, p.previous_gray = 'cpu', .4, True, None
        p.predictor = None
        pixels = np.zeros((100, 100, 3), dtype=np.uint8)
        for _ in range(2):
            output, metrics = p.process(pixels)
            self.assertEqual(output.shape, (100, 200, 3))
            self.assertEqual(metrics['objects'], 1)  # Excludes non-road classes.
            self.assertTrue(metrics['warning'])
            self.assertTrue(metrics['flow'])
            self.assertGreaterEqual(metrics['inferenceMs'], 0)
        self.assertFalse(pixels.any())  # Original camera buffer is never annotated.
        detections.clear()
        _, metrics = p.process(pixels)
        self.assertEqual(metrics['objects'], 0)
        self.assertFalse(metrics['warning'])


if __name__ == '__main__':
    unittest.main()
