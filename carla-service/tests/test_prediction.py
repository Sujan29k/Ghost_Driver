import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prediction import check_checkpoint


class CheckpointTest(unittest.TestCase):
    def test_missing_and_lfs_pointer_are_actionable_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'model.pth'
            with self.assertRaises(FileNotFoundError):
                check_checkpoint(path)
            path.write_text('version https://git-lfs.github.com/spec/v1\noid sha256:abc\n')
            with self.assertRaisesRegex(ValueError, 'Git LFS pointer'):
                check_checkpoint(path)


@unittest.skipUnless(all(importlib.util.find_spec(name) for name in ('cv2', 'numpy')), 'Install requirements-ai.txt')
class PredictionTest(unittest.TestCase):
    def test_timestamp_scaling_backward_direction_and_no_source_mutation(self):
        import numpy as np
        from prediction import PredictionView
        view = PredictionView('farneback', horizon_ms=200)
        pixels = np.zeros((128, 128, 3), dtype=np.uint8)
        pixels[80:100, 40:60] = 255
        original = pixels.copy()
        flow = np.zeros((128, 128, 2), dtype=np.float32)
        flow[..., 0] = -10  # Current -> previous: object moved right.
        view.flow = lambda *_: flow.copy()
        _, first = view.process(pixels, 0.0)
        output, second = view.process(pixels, 0.1)
        self.assertFalse(first['ready'])
        self.assertTrue(second['ready'])
        self.assertEqual(output[90, 70, 0], 255)  # 10 * (200/100) * .7 = 14px right.
        self.assertEqual(output[90, 42, 0], 0)
        np.testing.assert_array_equal(pixels, original)
        _, gap = view.process(pixels, 10.0)
        self.assertFalse(gap['ready'])
        _, reordered = view.process(pixels, 9.9)
        self.assertFalse(reordered['ready'])

    def test_real_farneback_is_finite_and_same_size(self):
        import numpy as np
        from prediction import PredictionView
        view = PredictionView('farneback')
        pixels = np.zeros((128, 128, 3), dtype=np.uint8)
        view.process(pixels, 1.0)
        output, metrics = view.process(pixels, 1.1)
        self.assertEqual(output.shape, pixels.shape)
        self.assertTrue(metrics['ready'])
        self.assertTrue(np.isfinite(output).all())
