import contextlib
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge import parse_args


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.env = {'SENDER_TOKEN': 'test-sender-'.ljust(40, 'x'), 'BACKEND_URL': 'https://sender.example.test',
                    'PREDICTION': 'raft', 'PREDICTION_MS': '300', 'AI_FPS': '10', 'TRAFFIC_CARS': '12'}

    def test_saved_gpu_profile_and_cli_overrides(self):
        args = parse_args([], self.env)
        self.assertEqual((args.prediction, args.prediction_ms, args.ai_fps, args.traffic), ('raft', 300, 10, 12))
        args = parse_args(['--prediction', 'off', '--traffic', '0'], self.env)
        self.assertEqual((args.prediction, args.traffic), ('off', 0))
        args = parse_args(['--ai-fps', '30', '--raft-iterations', '6'], self.env)
        self.assertEqual((args.ai_fps, args.raft_iterations), (30, 6))

    def test_bad_saved_values_fail_before_connecting(self):
        for key, value in [('PREDICTION', 'unknown'), ('AI_MODE', 'unknown'), ('AI_FPS', 'nan'),
                           ('TRAFFIC_CARS', '201'), ('CARLA_PORT', '0'), ('SENDER_TOKEN', ''),
                           ('RAFT_ITERATIONS', '0'), ('RAFT_ITERATIONS', '33')]:
            with self.subTest(key=key), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args([], {**self.env, key: value})

    def test_backend_requires_complete_base_url_without_secrets(self):
        for url in ['https://', 'https://host/api/health', 'http://remote.example',
                    'https://user:secret@host', 'https://host?token=secret', 'https://host:wrong', 'https://host:0']:
            with self.subTest(url=url), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args([], {**self.env, 'BACKEND_URL': url})
        self.assertEqual(parse_args([], {**self.env, 'BACKEND_URL': 'http://127.0.0.1:4000'}).port, 2000)
