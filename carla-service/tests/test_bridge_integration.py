"""Optional local aiortc integration. CARLA alone is stubbed; no simulator claim."""
import asyncio
import contextlib
import os
from pathlib import Path
import sys
import threading
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
        self.control = SimpleNamespace(throttle=0, brake=1, steer=0, gear=0)
        self.vehicle = SimpleNamespace(id=1, set_autopilot=lambda _: None,
            apply_control=self.apply, get_control=lambda: self.control,
            destroy=lambda: setattr(self, 'vehicle_destroyed', True))
        self.camera = SimpleNamespace(listen=self.listen, stop=self.camera_stop.set,
            destroy=lambda: setattr(self, 'camera_destroyed', True))
        blueprint = SimpleNamespace(set_attribute=lambda *_: None)
        actor = SimpleNamespace(get_velocity=lambda: SimpleNamespace(x=0, y=0, z=0),
            get_transform=lambda: SimpleNamespace(rotation=SimpleNamespace(yaw=0)))
        world = SimpleNamespace(
            wait_for_tick=lambda _: None,
            get_settings=lambda: SimpleNamespace(synchronous_mode=False),
            get_blueprint_library=lambda: SimpleNamespace(filter=lambda _: [blueprint], find=lambda _: blueprint),
            get_map=lambda: SimpleNamespace(get_spawn_points=lambda: [None]),
            try_spawn_actor=lambda *_: self.vehicle, spawn_actor=lambda *_, **__: self.camera,
            get_snapshot=lambda: SimpleNamespace(find=lambda _: actor, frame=self.frame,
                timestamp=SimpleNamespace(elapsed_seconds=self.frame / 30)))
        self.Client = lambda *_: SimpleNamespace(set_timeout=lambda _: None,
            get_client_version=lambda: 'test-only', get_server_version=lambda: 'test-only', get_world=lambda: world)
        self.VehicleControl = lambda **kw: SimpleNamespace(gear=0, **kw)
        self.Transform = lambda *_: None
        self.Location = lambda **_: None

    def apply(self, value):
        self.control = value

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

    async def exercise_bridge(self, ai, stall_inference=False):
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
            # Stub only inference here; test the real dedicated worker, frame
            # freshness, doubled output size and aiortc encode/decode path.
            def process(pixels, timestamp=None):
                if stall.is_set():
                    release_inference.wait(10)
                return np.hstack([pixels, pixels]), {
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
                pixel = first.to_ndarray(format='bgr24')[20, 20]
                self.assertGreater(int(pixel[2]), 200)
                self.assertLess(int(pixel[0]), 30)
                await operator.emit('stream:ready', {'sessionId': started['sessionId']})
                self.assertTrue((await operator.call('control:resume', {}))['success'])
                self.assertTrue((await operator.call('control:direct', {'sequence': 1, 'throttle': 1, 'brake': 0, 'steer': 0}))['success'])
                await asyncio.sleep(0.1)
                self.assertEqual(fake.control.throttle, 1)
                if stall_inference:
                    stall.set()
                else:
                    fake.paused = True
                self.assertEqual((await asyncio.wait_for(stops.get(), 5))['reason'], 'CARLA camera unavailable')
                await asyncio.sleep(0.1)
                self.assertEqual(fake.control.brake, 1)
        finally:
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
        self.assertTrue(fake.vehicle_destroyed)
        self.assertTrue(fake.camera_destroyed)


if __name__ == '__main__':
    unittest.main()
