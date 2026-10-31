import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmark_prediction import benchmark, load_sample
from prediction import warp_flow


class ReplayTest(unittest.TestCase):
    def sample(self, folder, previous=True):
        delayed = np.zeros((32, 256, 3), np.uint8)
        delayed[8:24, 20:40] = 255
        reference = np.zeros_like(delayed)
        reference[8:24, 120:140] = 255
        alignment = dict(previousTimestamp=0.0, delayedTimestamp=.05, referenceTimestamp=.30,
                         previousFrame=0, delayedFrame=1, referenceFrame=6,
                         delayMs=200, intervalMs=50, horizonMs=250)
        arrays = dict(delayed=delayed, reference=reference, alignment=np.array(json.dumps(alignment)))
        if previous:
            arrays['previous'] = delayed.copy()
        path = Path(folder) / 'frames-000000.npz'
        np.savez_compressed(path, **arrays)
        return path, delayed, reference

    def test_sweep_finds_known_translation_and_reuses_only_input_pair(self):
        with tempfile.TemporaryDirectory() as folder:
            path, delayed, target = self.sample(folder)
            calls = []
            def flow(previous, current):
                calls.append((previous.copy(), current.copy()))
                field = np.zeros((*current.shape[:2], 2), np.float32)
                field[..., 0] = -20
                return field
            rows, ranking, skipped = benchmark([path], SimpleNamespace(flow=flow), [.7, 1], [80, None])
            self.assertEqual(len(calls), 1)
            np.testing.assert_array_equal(calls[0][1], delayed)
            self.assertFalse(np.array_equal(calls[0][1], target))
            self.assertEqual(skipped, [])
            self.assertEqual((ranking[0]['scale'], ranking[0]['cap']), (1, None))
            self.assertEqual(ranking[0]['mae'], 0)
            self.assertEqual(ranking[0]['identicalSamples'], 1)
            capped = next(row for row in rows if row['scale'] == 1 and row['cap'] == 80)
            self.assertEqual(capped['cappedPercent'], 100)
            self.assertGreater(capped['mae'], 0)

    def test_legacy_samples_rejected_and_no_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            path, pixels, _ = self.sample(folder, previous=False)
            with self.assertRaisesRegex(ValueError, 'Missing previous'):
                load_sample(path)
            flow = np.full((*pixels.shape[:2], 2), -20, np.float32)
            original = flow.copy()
            _, fraction = warp_flow(pixels, flow, .05, 250)
            self.assertEqual(fraction, 1)
            np.testing.assert_array_equal(flow, original)

    def test_cli_writes_report_and_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            self.sample(folder)
            (Path(folder) / 'manifest.json').write_text('{}')
            output = Path(folder) / 'report'
            result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'benchmark_prediction.py'),
                                     folder, '--method', 'farneback', '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((output / 'report.json').read_text())
            self.assertEqual(len(report['ranking']), 7)
            self.assertEqual(report['skipped'], [])
            self.assertTrue((output / 'samples.csv').exists())
            self.assertIn('delayed', (output / 'report.md').read_text())


if __name__ == '__main__':
    unittest.main()
