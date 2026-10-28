"""Optional local aiortc integration. CARLA alone is stubbed; no simulator claim."""
import asyncio
import contextlib
import os
from pathlib import Path
import sys
import threading
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import numpy as np
    import socketio
    from aiortc import RTCPeerConnection, RTCConfiguration, RTCSessionDescription
    from aiortc.sdp import candidate_from_sdp
    AVAILABLE = True
except ImportError:
    AVAILABLE = False


class FakeCarla:
    """Small CARLA API fixture producing solid red test frames in memory."""
    def __init__(self):
        self.frame = 0
        self.paused = False
        self.vehicle_destroyed = self.camera_destroyed = False
        self.camera_stop = threading.Event()
        self.autopilot = False
        self.applied = 0
        self.location = SimpleNamespace(x=0, y=0, z=0)
        self.control = SimpleNamespace(throttle=0, brake=1, steer=0, gear=0, reverse=False)
        self.vehicle = SimpleNamespace(id=1, set_autopilot=lambda enabled, *_: setattr(self, 'autopilot', enabled),
            get_velocity=lambda: SimpleNamespace(x=0, y=0, z=0), get_location=lambda: self.location,
            is_at_traffic_light=lambda: False,
            apply_control=self.apply, get_control=lambda: self.control,
            destroy=lambda: setattr(self, 'vehicle_destroyed', True))
        self.camera = SimpleNamespace(listen=self.listen, stop=self.camera_stop.set,
            destroy=lambda: setattr(self, 'camera_destroyed', True))
        blueprint = lambda name: SimpleNamespace(id=name, set_attribute=lambda *_: None)
        def waypoint(x=0):
            return SimpleNamespace(road_id=1, section_id=0, lane_id=1, s=x, lane_width=3.5,
                transform=SimpleNamespace(location=SimpleNamespace(x=x, y=0, z=0), rotation=SimpleNamespace(yaw=0)),
                next=lambda step: [waypoint(x + step)])
        self.weather = SimpleNamespace(cloudiness=0, precipitation=0, precipitation_deposits=0, wetness=0,
                                       fog_density=0, sun_altitude_angle=60)
        self.sensors = []
        def spawn(bp, *_args, **_kwargs):
            if bp.id == 'sensor.camera.rgb':
                return self.camera
            sensor = SimpleNamespace(id=len(self.sensors) + 3, is_alive=True, listen=lambda _: None,
                stop=lambda: None)
            sensor.destroy = lambda: setattr(sensor, 'is_alive', False)
            self.sensors.append(sensor)
            return sensor
        actor = SimpleNamespace(get_velocity=lambda: SimpleNamespace(x=0, y=0, z=0),
            get_transform=lambda: SimpleNamespace(rotation=SimpleNamespace(yaw=0)))
        world = SimpleNamespace(
            wait_for_tick=lambda _: None,
            get_settings=lambda: SimpleNamespace(synchronous_mode=False),
            get_blueprint_library=lambda: SimpleNamespace(filter=lambda name: [blueprint(name)], find=blueprint),
            get_map=lambda: SimpleNamespace(name='FixtureMap', get_spawn_points=lambda: [None], get_waypoint=lambda loc: waypoint(loc.x)),
            get_weather=lambda: SimpleNamespace(**vars(self.weather)), set_weather=lambda value: setattr(self, 'weather', value),
            try_spawn_actor=lambda *_: self.vehicle, spawn_actor=spawn,
            get_snapshot=lambda: SimpleNamespace(find=lambda _: actor, frame=self.frame,
                timestamp=SimpleNamespace(elapsed_seconds=self.frame / 30)))
        tm = SimpleNamespace(set_path=lambda *_: None, auto_lane_change=lambda *_: None,
            vehicle_percentage_speed_difference=lambda *_: None, distance_to_leading_vehicle=lambda *_: None)
        self.Client = lambda *_: SimpleNamespace(set_timeout=lambda _: None, get_trafficmanager=lambda _: tm,
            get_client_version=lambda: '0.9.15', get_server_version=lambda: '0.9.15', get_world=lambda: world)
        self.VehicleControl = lambda **kw: SimpleNamespace(**{**dict(throttle=0, brake=0, steer=0, reverse=False, gear=-1 if kw.get('reverse') else 1), **kw})
        self.Transform = lambda *_: None
        self.Location = lambda **kw: SimpleNamespace(**{**dict(x=0, y=0, z=0), **kw})

    def apply(self, value):
        self.control = value
        self.applied += 1

    def listen(self, callback):
        def produce():
            pixels = np.zeros((48, 64, 4), dtype=np.uint8)
            pixels[:, :, 2:] = 255  # BGRA red, opaque.
            while not self.camera_stop.wait(1 / 30):
                if self.paused:
                    continue
                self.frame += 1
                callback(SimpleNamespace(frame=self.frame, timestamp=self.frame / 30,
                                         raw_data=pixels.tobytes(), width=64, height=48))
        self.thread = threading.Thread(target=produce, daemon=True)
        self.thread.start()


@unittest.skipUnless(AVAILABLE, 'Install carla-service/requirements.txt for the optional aiortc integration test')
class BridgeIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_python_signaling_frames_camera_loss_and_cleanup(self):
        await self.exercise_bridge(False)

    async def test_processed_frames_camera_loss_and_cleanup(self):
        await self.exercise_bridge(True)

    async def test_stalled_inference_stops_video_while_camera_is_alive(self):
        await self.exercise_bridge(True, stall_inference=True)

    async def test_research_reverse_autonomy_scenario_takeover_and_camera_loss(self):
        await self.exercise_bridge(True, research_mode=True)

    async def exercise_bridge(self, ai, stall_inference=False, research_mode=False):
        import bridge
        root = Path(__file__).resolve().parents[2]
        env = {**os.environ, 'DASHBOARD_TOKEN': 'integration-dashboard-token-0000000000',
            'SENDER_TOKEN': 'integration-sender-token-0000000000000', 'STUN_URL': '',
            'TURN_URL': '', 'TURN_USERNAME': '', 'TURN_PASSWORD': '', 'ALLOW_DEMO': 'false'}
        server = await asyncio.create_subprocess_exec('node', '-e',
            "const app = require('./backend/src/server').createServer(); "
            "app.server.listen(0, '127.0.0.1', () => console.log(app.server.address().port)); "
            "process.on('SIGTERM', () => app.close().then(() => process.exit()));",
            cwd=root, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        operator = socketio.AsyncClient()
        peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        fake = FakeCarla()
        task = None
        frames = asyncio.Queue()
        offers = asyncio.Queue()
        stops = asyncio.Queue()
        vehicles = []
        candidates = []
        stall = threading.Event()
        release_inference = threading.Event()
        recording_dir = tempfile.TemporaryDirectory()
        telemetry = {}
        heartbeat = None

        @operator.on('telemetry:update')
        async def observed(data):
            telemetry.update(data)

        @operator.on('vehicles:list')
        async def discovered(data):
            vehicles[:] = data

        @operator.on('webrtc:offer')
        async def offered(data):
            await offers.put(data)

        @operator.on('stream:stopped')
        async def stopped(data):
            await stops.put(data)

        @operator.on('webrtc:ice-candidate')
        async def ice(data):
            value = data['candidate']
            candidate = candidate_from_sdp(value['candidate'].removeprefix('candidate:'))
            candidate.sdpMid, candidate.sdpMLineIndex = value['sdpMid'], value['sdpMLineIndex']
            if peer.remoteDescription:
                await peer.addIceCandidate(candidate)
            else:
                candidates.append(candidate)

        @peer.on('track')
        def track_received(track):
            async def consume():
                while True:
                    await frames.put(await track.recv())
            consumer = asyncio.create_task(consume())
            consumer.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

        try:
            port_line = await asyncio.wait_for(server.stdout.readline(), 5)
            if not port_line:
                self.fail((await server.stderr.read()).decode())
            port = int(port_line)
            url = f'http://127.0.0.1:{port}'
            await operator.connect(url, auth={'role': 'dashboard', 'token': env['DASHBOARD_TOKEN']}, transports=['websocket'])
            args = SimpleNamespace(backend=url, token=env['SENDER_TOKEN'], host='127.0.0.1', port=2000,
                name='CARLA API fixture (test only)', vehicle='test', width=64, height=48,
                ai='yolo' if ai else 'off', weights='fixture', device='cpu', confidence=0.4, optical_flow=True)
            if research_mode:
                args.research = True
                args.video_delay, args.prediction, args.view, args.show_reference = 200, 'farneback', 'compare', False
                args.raft_weights, args.record_dir = 'fixture', recording_dir.name
                args.tm_port, args.seed, args.direction_speed_limit = 8000, 2026, 1
            # Stub only inference here; test the real dedicated worker, frame
            # freshness, doubled output size and aiortc encode/decode path.
            def process(pixels, timestamp=None):
                if stall.is_set():
                    release_inference.wait(10)
                return (pixels.copy() if research_mode else np.hstack([pixels, pixels])), {
                    'enabled': True, 'objects': 2, 'inferenceMs': 1, 'flow': True, 'warning': False}
            processor = SimpleNamespace(process=process)
            with patch.dict(sys.modules, {'carla': fake}), patch('perception.Perception', return_value=processor):
                task = asyncio.create_task(bridge.run(args))
                deadline = time.monotonic() + 10
                while not vehicles or not vehicles[0]['ready']:
                    if task.done():
                        await task
                    self.assertLess(time.monotonic(), deadline, 'Sender never became ready')
                    await asyncio.sleep(0.05)
                self.assertTrue((await operator.call('vehicle:connect', {'vehicleId': vehicles[0]['id']}))['emergency'])
                started = await operator.call('stream:request', {'vehicleId': vehicles[0]['id']})
                self.assertTrue(started['success'])
                offer = await asyncio.wait_for(offers.get(), 10)
                await peer.setRemoteDescription(RTCSessionDescription(**offer['sdp']))
                for candidate in candidates:
                    await peer.addIceCandidate(candidate)
                await peer.setLocalDescription(await peer.createAnswer())
                await operator.emit('webrtc:answer', {'sessionId': started['sessionId'],
                    'sdp': {'type': peer.localDescription.type, 'sdp': peer.localDescription.sdp}})
                first = await asyncio.wait_for(frames.get(), 10)
                second = await asyncio.wait_for(frames.get(), 5)
                self.assertEqual((first.width, first.height), (128 if ai else 64, 48))
                self.assertGreater(second.pts, first.pts)
                pixel = first.to_ndarray(format='bgr24')[46, 50]
                self.assertGreater(int(pixel[2]), 200)
                self.assertLess(int(pixel[0]), 30)
                await operator.emit('stream:ready', {'sessionId': started['sessionId']})
                await asyncio.sleep(.3)
                self.assertTrue((await operator.call('control:resume', {}))['success'])
                self.assertTrue((await operator.call('control:direct', {'sequence': 1, 'throttle': 1, 'brake': 0, 'steer': 0}))['success'])
                await asyncio.sleep(0.1)
                self.assertEqual(fake.control.throttle, 1)
                if research_mode:
                    async def supervision():
                        while True:
                            await asyncio.sleep(.15)
                            await operator.emit('stream:ready', {'sessionId': started['sessionId']})
                    heartbeat = asyncio.create_task(supervision())
                    async def command(action, data):
                        result = await operator.call('research:command', {'action': action, 'data': data}, timeout=10)
                        self.assertTrue(result['success'], result)
                        return result['state']
                    await command('direction', {'direction': 'reverse'})
                    await command('mode', {'mode': 'MANUAL'})
                    await operator.call('control:direct', {'sequence': 2, 'throttle': 1, 'brake': 0, 'steer': 0})
                    await asyncio.sleep(.1)
                    self.assertTrue(fake.control.reverse)
                    self.assertEqual(fake.control.throttle, 1)
                    await command('direction', {'direction': 'forward'})
                    await command('mode', {'mode': 'AUTONOMOUS'})
                    self.assertTrue(fake.autopilot)
                    count = fake.applied
                    await asyncio.sleep(.25)
                    self.assertEqual(fake.applied, count, 'Manual loop overwrote Traffic Manager')
                    await command('trial', {'operation': 'start', 'label': 'fixture-only', 'saveFrames': True, 'order': 1})
                    state = await command('scenario', {'operation': 'start', 'name': 'rain', 'severity': 3, 'seed': 2026, 'blockage': 'partial'})
                    self.assertEqual(state['mode'], 'AUTONOMOUS')
                    deadline = time.monotonic() + 4
                    while telemetry.get('research', {}).get('mode') != 'TAKEOVER_REQUESTED':
                        self.assertLess(time.monotonic(), deadline, telemetry)
                        await asyncio.sleep(.05)
                    self.assertFalse(fake.autopilot)
                    self.assertEqual(fake.control.brake, 1)
                    self.assertEqual(telemetry['research']['takeover']['source'], 'scripted')
                    await command('mode', {'mode': 'MANUAL'})
                    await command('scenario', {'operation': 'reset', 'name': 'none', 'severity': 1, 'seed': 2026, 'blockage': 'partial'})
                    await command('mode', {'mode': 'AUTONOMOUS'})
                    self.assertTrue(fake.autopilot)
                if stall_inference:
                    stall.set()
                else:
                    fake.paused = True
                self.assertEqual((await asyncio.wait_for(stops.get(), 5))['reason'], 'CARLA camera unavailable')
                await asyncio.sleep(0.1)
                self.assertEqual(fake.control.brake, 1)
                if research_mode:
                    self.assertFalse(fake.autopilot)
        finally:
            if heartbeat:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat
            release_inference.set()
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await operator.shutdown()
            await peer.close()
            if server.returncode is None:
                server.terminate()
            await asyncio.wait_for(server.wait(), 5)
            recording_dir.cleanup()
        self.assertTrue(fake.vehicle_destroyed)
        self.assertTrue(fake.camera_destroyed)


if __name__ == '__main__':
    unittest.main()
