import sys
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comparison import ComparisonPipeline, FrameHistory, Observation
from control_state import ControlState
from recording import TrialRecorder
from research import ResearchController
from takeover import TakeoverPolicy


class HistoryTest(unittest.TestCase):
    def test_selects_observation_at_or_before_cutoff_and_resets_timestamp(self):
        history = FrameHistory(max_frames=10)
        for i, t in enumerate([0, .07, .19, .31, .47]):
            history.append(Observation(t, i, np.full((8, 8, 3), i, np.uint8), 1, 192))
        previous, delayed, reference = history.select(200)
        self.assertEqual((previous.frame_id, delayed.frame_id, reference.frame_id), (1, 2, 4))
        self.assertLessEqual(delayed.timestamp, reference.timestamp - .2)
        self.assertIsNone(history.select(800))
        history.append(Observation(0, 0, None, 2, 0))
        self.assertEqual(len(history.frames), 1)

    def test_predictor_only_receives_delayed_and_earlier_frames_with_actual_horizon(self):
        pipeline = ComparisonPipeline(delay_ms=200, method='farneback')
        imgs = [np.full((32, 32, 3), n, np.uint8) for n in (1, 2, 3, 4)]
        for i, timestamp in enumerate((0, .12, .25, .51)):
            pipeline.history.append(Observation(timestamp, i, imgs[i], time.monotonic(), imgs[i].nbytes))
        seen = {}
        class Predictor:
            def __init__(self, *_a, **_kw): pass
            def predict_pair(self, previous, delayed, interval, horizon):
                seen.update(previous=int(previous[0, 0, 0]), delayed=int(delayed[0, 0, 0]), interval=interval, horizon=horizon)
                return delayed.copy()
        with patch('prediction.PredictionView', Predictor):
            output, details, samples, _ = pipeline.process(evaluate=True)
        self.assertEqual((seen['previous'], seen['delayed']), (2, 3))
        self.assertAlmostEqual(seen['interval'], .13)
        self.assertAlmostEqual(seen['horizon'], 260)
        self.assertEqual(details['referenceFrame'], 3)
        self.assertEqual(details['delayedFrame'], 2)
        self.assertNotEqual(seen['delayed'], int(samples['reference'][0, 0, 0]))
        self.assertEqual(int(samples['previous'][0, 0, 0]), seen['previous'])
        self.assertEqual(samples['predicted'].shape, samples['reference'].shape)
        self.assertIsNotNone(output)
        self.assertNotIn('metrics', details)  # Scoring belongs to the recorder worker.

    def test_reset_during_inference_invalidates_frame_even_when_settings_unchanged(self):
        pipeline = ComparisonPipeline(delay_ms=100, method='farneback')
        for i, t in enumerate((0, .1, .2, .3)):
            pixels = np.full((32, 32, 3), i, np.uint8)
            pipeline.history.append(Observation(t, i, pixels, time.monotonic(), pixels.nbytes))
        class Predictor:
            def predict_pair(self, previous, delayed, interval, horizon):
                pipeline.history.clear()
                return delayed
        pipeline.predictors['farneback'] = Predictor()
        output, details, samples, _ = pipeline.process(evaluate=True)
        self.assertIsNone(output)
        self.assertIsNone(samples)
        self.assertEqual(details['status'], 'stale-or-reset')

    def test_single_baseline_does_not_run_prediction_and_memory_is_bounded(self):
        pipeline = ComparisonPipeline(delay_ms=0, method='raft', view='delayed')
        pipeline.history = FrameHistory(max_frames=3, max_bytes=2 * 32 * 32 * 3)
        for i in range(5):
            img = np.zeros((32, 32, 3), np.uint8)
            pipeline.history.append(Observation(i * .1, i, img, time.monotonic(), img.nbytes))
        with patch('prediction.PredictionView', side_effect=AssertionError('Unused inference')):
            output, details, _, _ = pipeline.process(evaluate=True)
        self.assertIsNotNone(output)
        self.assertEqual(details['predictionMs'], 0)
        self.assertEqual(len(pipeline.history.frames), 2)

    def test_all_video_views_keep_dimensions_and_reference_out_of_predictor(self):
        for view, reference, panels in [('delayed', False, 1), ('predicted', False, 1),
                                       ('reference', False, 1), ('compare', False, 2), ('compare', True, 3)]:
            with self.subTest(view=view, reference=reference):
                pipeline = ComparisonPipeline(delay_ms=100, method='farneback', view=view, reference=reference)
                for i, t in enumerate((0, .1, .2)):
                    pixels = np.full((64, 64, 3), i, np.uint8)
                    pipeline.history.append(Observation(t, i, pixels, time.monotonic(), pixels.nbytes))
                calls = []
                def predict(previous, delayed, *_):
                    calls.append((int(previous[0, 0, 0]), int(delayed[0, 0, 0])))
                    return delayed.copy()
                pipeline.predictors['farneback'] = SimpleNamespace(predict_pair=predict)
                output, _, samples, _ = pipeline.process(evaluate=False)
                self.assertEqual(output.shape, (64, 64 * panels, 3))
                self.assertIsNone(samples)
                self.assertEqual(calls, [(0, 1)] if view in ('predicted', 'compare') else [])

    def test_status_ages_without_waiting_for_stalled_inference(self):
        pipeline = ComparisonPipeline(delay_ms=0, method='farneback')
        image = np.zeros((32, 32, 3), np.uint8)
        pipeline.history.append(Observation(1, 1, image, time.monotonic(), image.nbytes))
        _, details, _, _ = pipeline.process()
        self.assertTrue(pipeline.report(details)['predictionReady'])
        with patch('comparison.time.monotonic', return_value=details['sourceCapturedAt'] + 2.1):
            self.assertEqual(pipeline.report(details)['status'], 'stale')
            self.assertFalse(pipeline.report(details)['predictionReady'])
        pipeline.history.clear()
        self.assertEqual(pipeline.report(details)['status'], 'buffering')

    def test_delay_reset_clears_history_and_comparison_states_unavailable(self):
        pipeline = ComparisonPipeline(delay_ms=800, method='off')
        img = np.zeros((32, 32, 3), np.uint8)
        pipeline.history.append(Observation(1, 1, img, time.monotonic(), img.nbytes))
        output, details, _, _ = pipeline.process()
        self.assertIsNone(output)
        self.assertEqual(details['status'], 'buffering')
        pipeline.configure(0, 'off', 'delayed')
        self.assertEqual(len(pipeline.history.frames), 0)


class SafetyAndResearchTest(unittest.TestCase):
    def autonomy_fixture(self, folder):
        controls = ControlState(timeout=5)
        controls.supervise()
        state = SimpleNamespace(autopilot=False, synchronous=True, applied=None)
        location = SimpleNamespace(x=0, y=0, z=0)
        vehicle = SimpleNamespace(get_velocity=lambda: location, get_location=lambda: location,
            apply_control=lambda value: setattr(state, 'applied', value),
            set_autopilot=lambda enabled, *_: setattr(state, 'autopilot', enabled),
            is_at_traffic_light=lambda: False)
        def path(*_):
            self.assertFalse(state.synchronous)
            self.assertTrue(state.autopilot)
            self.assertEqual(state.applied.brake, 0)
        tm = SimpleNamespace(set_synchronous_mode=lambda value: setattr(state, 'synchronous', value),
            set_path=path, auto_lane_change=lambda *_: None,
            vehicle_percentage_speed_difference=lambda *_: None, distance_to_leading_vehicle=lambda *_: None)
        world = SimpleNamespace(get_map=lambda: None)
        carla = SimpleNamespace(VehicleControl=lambda **kw: SimpleNamespace(**kw))
        controller = ResearchController(world, SimpleNamespace(get_trafficmanager=lambda _: tm),
                                        carla, vehicle, controls, None, folder)
        controller.routes = SimpleNamespace(name='straight', points=[location], length=300, options=[],
            select=lambda _: None, snapshot=lambda: {},
            observe=lambda _: dict(progress=0, deviation=0, finished=False))
        return controller, controls, state, tm

    def test_autonomous_start_hazard_stop_and_deliberate_manual_takeover(self):
        with tempfile.TemporaryDirectory() as folder:
            controller, controls, state, _ = self.autonomy_fixture(folder)
            controller.command(dict(action='mode', data={'mode': 'AUTONOMOUS'}, commandId=1))
            self.assertTrue(state.autopilot)
            applied = state.applied
            controller.tick()
            self.assertIs(state.applied, applied)  # Manual loop must not overwrite Traffic Manager.
            controller.scenarios.hazard = controller.vehicle.get_location()
            controller.tick()
            self.assertEqual(controls.snapshot()['mode'], 'TAKEOVER_REQUESTED')
            self.assertFalse(state.autopilot)
            self.assertEqual(state.applied.brake, 1)
            controller.command(dict(action='mode', data={'mode': 'MANUAL'}, commandId=2))
            controls.accept(dict(commandId=3, throttle=.5, brake=0, steer=0))
            controller.tick()
            self.assertEqual(state.applied.throttle, .5)
            self.assertFalse(state.autopilot)

    def test_failed_or_cancelled_autonomy_start_disables_tm_and_brakes(self):
        for cancel in (False, True):
            with self.subTest(cancel=cancel), tempfile.TemporaryDirectory() as folder:
                controller, controls, state, tm = self.autonomy_fixture(folder)
                def fail(*_):
                    if cancel:
                        controls.stop('Emergency stop')
                    else:
                        raise RuntimeError('Route RPC failed')
                tm.set_path = fail
                with self.assertRaises((RuntimeError, ValueError)):
                    controller.command(dict(action='mode', data={'mode': 'AUTONOMOUS'}, commandId=1))
                self.assertFalse(state.autopilot)
                self.assertTrue(controls.is_latched())
                self.assertEqual(state.applied.brake, 1)

    def test_manual_authority_never_overwrites_autonomy_and_fresh_supervision_expires(self):
        state = ControlState(timeout=.05)
        state.supervise()
        generation = state.begin_operation(10)
        state.transition('AUTONOMOUS', generation)
        self.assertFalse(state.accept({'commandId': 11, 'throttle': 1, 'brake': 0, 'steer': 0}))
        time.sleep(.07)
        self.assertEqual(state.current(), (0, 1, 0))
        self.assertEqual(state.snapshot()['mode'], 'STOPPED')
        self.assertTrue(state.latched)

    def test_emergency_invalidates_pending_transition_and_reconnect_does_not_resume(self):
        state = ControlState()
        old_generation = state.begin_operation(4)
        state.stop('Operator connection lost')
        with self.assertRaisesRegex(ValueError, 'cancelled'):
            state.transition('AUTONOMOUS', old_generation)
        self.assertTrue(state.latched)
        state.reset()
        self.assertTrue(state.latched)
        self.assertEqual(state.snapshot()['mode'], 'STOPPED')
        with self.assertRaisesRegex(ValueError, 'Queued operation cancelled'):
            state.begin_operation(5, expected_generation=old_generation)

    def test_stop_and_disconnect_latch_every_mode_until_explicit_action(self):
        for mode in ('STOPPED', 'MANUAL', 'AUTONOMOUS', 'TAKEOVER_REQUESTED', 'EMERGENCY_STOP'):
            for reason in ('Emergency stop', 'Operator connection lost', 'Required monitoring video unavailable'):
                with self.subTest(mode=mode, reason=reason):
                    state = ControlState()
                    state.supervise()
                    state.transition(mode, state.generation)
                    state.accept({'commandId': 1, 'throttle': 0, 'brake': 1, 'steer': 0, 'emergency': True, 'reason': reason})
                    state.supervise()
                    state.accept({'commandId': 2, 'throttle': 1, 'brake': 0, 'steer': 0})
                    self.assertTrue(state.is_latched())
                    self.assertEqual(state.current(), (0, 1, 0))

    def test_direction_change_rejects_motion_and_applies_reverse_flag_only_at_rest(self):
        class Vehicle:
            def __init__(self):
                self.velocity = SimpleNamespace(x=0.0, y=0.0, z=0.0)
                self.applied = None
            def get_velocity(self): return self.velocity
            def get_location(self): return SimpleNamespace(x=0, y=0, z=0)
            def set_autopilot(self, *_): pass
            def apply_control(self, control): self.applied = control
            def get_control(self): return SimpleNamespace(throttle=0, brake=1, steer=0, gear=-1 if getattr(self.applied, 'reverse', False) else 0)
        class World:
            def get_map(self): return SimpleNamespace()
        carla = SimpleNamespace(VehicleControl=lambda **kw: SimpleNamespace(**kw))
        vehicle, controls = Vehicle(), ControlState()
        with tempfile.TemporaryDirectory() as directory:
            controller = ResearchController(World(), SimpleNamespace(), carla, vehicle, controls, None, directory, direction_limit=1)
            vehicle.velocity.x = 1.0  # 3.6 km/h
            with self.assertRaisesRegex(ValueError, 'Stop below 1 km/h'):
                controller.command({'action': 'direction', 'data': {'direction': 'reverse'}, 'commandId': 1})
            self.assertFalse(controls.reverse)
            vehicle.velocity.x = .1  # 0.36 km/h
            state = controller.command({'action': 'direction', 'data': {'direction': 'reverse'}, 'commandId': 2})
            self.assertTrue(controls.reverse)
            self.assertEqual(state['direction'], 'reverse')
            # Reverse is an explicit CARLA flag; throttle remains nonnegative.
            controls.transition('MANUAL', controls.generation)
            self.assertTrue(controls.accept({'commandId': 3, 'throttle': 1, 'brake': 0, 'steer': 0}))
            throttle, _, _ = controls.current()
            self.assertEqual(throttle, 1)
            controls.stop('test')
            controller.close()

    def test_reverse_is_explicit_and_key_controls_do_not_set_negative_throttle(self):
        state = ControlState()
        gen = state.begin_operation(1)
        state.transition('MANUAL', gen)
        state.reverse = True
        state.accept({'commandId': 2, 'throttle': 1, 'brake': 0, 'steer': 0})
        throttle, brake, _ = state.current()
        self.assertEqual((throttle, brake), (1, 0))
        self.assertTrue(state.reverse)
        with state.lock:
            state.reverse = False
        self.assertFalse(state.reverse)

    def test_policy_debounces_hazards_and_ignores_red_light_stall(self):
        policy = TakeoverPolicy(stallSeconds=3, blockedSeconds=1)
        self.assertIsNone(policy.evaluate(progress=0, speed=0, at_red_light=True, now=0))
        self.assertIsNone(policy.evaluate(progress=0, speed=0, blocked=True, at_red_light=True, now=5))
        self.assertIsNone(policy.evaluate(progress=0, speed=0, blocked=True, now=6))
        trigger = policy.evaluate(progress=0, speed=0, blocked=True, now=7.1)
        self.assertEqual(trigger['source'], 'sensor')
        self.assertEqual(policy.evaluate(progress=0, speed=0, collision=True)['source'], 'sensor')

    def test_trial_writer_flushes_clocked_jsonl_events_and_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = TrialRecorder(directory)
            started = recorder.start({'map': 'Town01', 'seed': 7}, 'delayed', True, 2)
            recorder.record('takeover:trigger', {'senderMonotonicNs': time.monotonic_ns()})
            img = np.zeros((32, 32, 3), np.uint8)
            recorder.frame({'referenceTimestamp': .5, 'horizonMs': 200}, {'reference': img, 'delayed': img})
            ended = recorder.stop()
            folder = Path(directory) / started['id']
            rows = [__import__('json').loads(line) for line in (folder / 'events.jsonl').read_text().splitlines()]
            self.assertTrue(any(row['kind'] == 'takeover:trigger' for row in rows))
            self.assertTrue((folder / 'frames-000000.npz').is_file())
            self.assertFalse(ended['active'])
            self.assertIn('asynchronous', (folder / 'manifest.json').read_text())

    def test_evaluation_scores_baseline_and_rejects_future_or_mismatched_images(self):
        from evaluate_trials import evaluate
        with tempfile.TemporaryDirectory() as directory:
            recorder = TrialRecorder(directory)
            started = recorder.start({'map': 'Town01'}, save_frames=True)
            frame = {'epoch': 1, 'revision': 1, 'referenceTimestamp': .5, 'delayedTimestamp': .3,
                     'previousTimestamp': .2, 'referenceFrame': 5, 'delayedFrame': 3, 'previousFrame': 2,
                     'horizonMs': 200, 'intervalMs': 100, 'delayMs': 200}
            img = np.zeros((32, 32, 3), np.uint8)
            recorder.frame(frame, {'reference': img, 'delayed': img.copy()})
            recorder.stop()
            folder = Path(directory) / started['id']
            result = evaluate(folder)['visualReconstruction']
            self.assertEqual(result['delayedOnlySamples'], 1)
            self.assertEqual(result['allDelayed']['mae'], 0)
            self.assertEqual(result['pairedSamples'], 0)
            path = folder / 'events.jsonl'
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            evaluation = next(row for row in rows if row['kind'] == 'frame:evaluation')
            evaluation['data']['referenceFrame'] = 99
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            result = evaluate(folder)['visualReconstruction']
            self.assertEqual(result['alignedSamples'], 0)
            self.assertIn('identifiers', result['alignmentErrors'][0]['reason'])
            evaluation['data']['delayedTimestamp'] = .45
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            self.assertIn('cutoff', evaluate(folder)['visualReconstruction']['alignmentErrors'][0]['reason'])

    def test_recording_snapshots_mutable_events_and_reports_worse_prediction(self):
        from evaluate_trials import evaluate
        with tempfile.TemporaryDirectory() as directory:
            recorder = TrialRecorder(directory)
            state = recorder.start({}, save_frames=False)
            data = {'triggerNs': time.monotonic_ns(), 'source': 'scripted', 'reason': 'zone'}
            recorder.record('takeover:trigger', data)
            recorder.record('takeover:acknowledged', {'triggerNs': data['triggerNs']})
            data['reason'] = 'mutated'
            img = np.zeros((32, 32, 3), np.uint8)
            recorder.frame({'referenceTimestamp': .5, 'delayedTimestamp': .3, 'previousTimestamp': .2,
                'referenceFrame': 5, 'delayedFrame': 3, 'previousFrame': 2, 'horizonMs': 200,
                'intervalMs': 100, 'delayMs': 200}, {'reference': img, 'delayed': img.copy(), 'predicted': img + 10})
            recorder.stop()
            result = evaluate(Path(directory) / state['id'])
            self.assertEqual(result['visualReconstruction']['predictionWorseCases'], 1)
            self.assertEqual(result['taskPerformance']['takeovers'][0]['reason'], 'zone')
            self.assertIsNotNone(result['taskPerformance']['takeovers'][0]['manualAcknowledgementMs'])

if __name__ == '__main__':
    unittest.main()
