"""CARLA RGB/control provider for GhostDriver; no YOLO or prediction dependency."""
import argparse
import asyncio
import logging
import math
import os
from pathlib import Path
from fractions import Fraction
from urllib.parse import urlparse
import threading
import time
from control_state import ControlState

log = logging.getLogger('ghostdriver')


async def run(args):
    # Keep --help usable before the optional dependencies are installed.
    import carla
    import numpy as np
    import socketio
    from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer, VideoStreamTrack
    from aiortc.sdp import candidate_from_sdp
    from av import VideoFrame

    vehicle = camera = None
    worker = None
    quit_event = threading.Event()
    controls = ControlState()
    image_lock = threading.Lock()
    latest = {'image': None, 'image_at': 0, 'telemetry': None, 'telemetry_at': 0, 'error': None}
    ice_servers = []
    status_task = None
    setup_task = None
    world = None
    sio = socketio.AsyncClient(reconnection=True)
    pc = None
    track = None
    session_id = None
    candidates = []
    rtc_lock = asyncio.Lock()
    registration_lock = asyncio.Lock()

    class CameraTrack(VideoStreamTrack):
        async def recv(self):
            # Never manufacture placeholder frames or replay a stalled camera forever.
            while True:
                with image_lock:
                    image = latest['image']
                    fresh = time.monotonic() - latest['image_at'] < 2
                if image is not None and fresh and image.frame != getattr(self, 'last_frame', None):
                    break
                await asyncio.sleep(0.01)
            self.last_frame = image.frame
            pixels = np.frombuffer(image.raw_data, dtype=np.uint8).reshape(image.height, image.width, 4)[:, :, :3].copy()
            frame = VideoFrame.from_ndarray(pixels, format='bgr24')
            if not hasattr(self, 'started_at'):
                self.started_at = time.monotonic()
            frame.pts = int((time.monotonic() - self.started_at) * 90000)
            frame.time_base = Fraction(1, 90000)
            return frame

    async def close_stream():
        nonlocal pc, track, session_id, candidates
        old_pc, old_track = pc, track
        pc = track = session_id = None
        candidates = []
        controls.stop()
        if old_track:
            old_track.stop()
        if old_pc:
            await old_pc.close()

    async def register():
        nonlocal ice_servers
        if registration_lock.locked():
            return
        async with registration_lock:
            controls.reset()
            config = await sio.call('rtc:config', {}, timeout=10)
            if not config.get('success'):
                raise RuntimeError('Could not load authenticated ICE configuration')
            ice_servers = config['iceServers']
            result = await sio.call('vehicle:join', {'name': args.name, 'mode': 'carla'}, timeout=5)
            if not result.get('success'):
                raise RuntimeError(result.get('message', 'Vehicle registration failed'))
            log.info('Registered. Open the dashboard, connect, and start video.')

    @sio.event
    async def connect():
        await register()

    @sio.on('vehicle:registration-required')
    async def registration_required(_data):
        await register()

    @sio.event
    async def disconnect(*_args):
        controls.stop()
        await close_stream()
        log.warning('Backend disconnected; applying brakes')

    @sio.on('control:apply')
    async def apply_control(data):
        controls.accept(data)

    @sio.on('stream:start')
    async def start_stream(data):
        nonlocal pc, track, session_id
        async with rtc_lock:
            await close_stream()
            session_id = data['sessionId']
            current_id = session_id
            try:
                servers = [RTCIceServer(**server) for server in ice_servers]
                peer = RTCPeerConnection(RTCConfiguration(iceServers=servers))
                pc = peer
                track = CameraTrack()
                peer.addTrack(track)

                @peer.on('connectionstatechange')
                async def connection_changed():
                    if pc is peer and peer.connectionState in ('failed', 'disconnected', 'closed'):
                        controls.stop()
                        await sio.emit('stream:error', {'sessionId': current_id, 'message': 'CARLA video connection failed'})

                await peer.setLocalDescription(await peer.createOffer())
                # aiortc gathers ICE during setLocalDescription. Send the gathered SDP.
                if pc is peer:
                    await sio.emit('webrtc:offer', {'sessionId': current_id,
                        'sdp': {'type': peer.localDescription.type, 'sdp': peer.localDescription.sdp}})
            except Exception as exc:
                log.error('Unable to start video (%s)', type(exc).__name__)
                await sio.emit('stream:error', {'sessionId': current_id, 'message': 'Sender WebRTC failed; check ICE configuration and sender logs'})
                await close_stream()

    @sio.on('webrtc:answer')
    async def answer(data):
        nonlocal candidates
        async with rtc_lock:
            if pc is None or data['sessionId'] != session_id:
                return
            try:
                await pc.setRemoteDescription(RTCSessionDescription(**data['sdp']))
                for candidate in candidates:
                    await pc.addIceCandidate(candidate)
                candidates = []
            except Exception as exc:
                log.error('Invalid WebRTC answer (%s)', type(exc).__name__)
                await sio.emit('stream:error', {'sessionId': session_id, 'message': 'Sender WebRTC failed; check ICE configuration and sender logs'})
                await close_stream()

    @sio.on('webrtc:ice-candidate')
    async def ice(data):
        if pc is None or data['sessionId'] != session_id or not data.get('candidate'):
            return
        try:
            value = data['candidate']
            raw = value.get('candidate', '')
            if not raw:
                return
            candidate = candidate_from_sdp(raw.removeprefix('candidate:'))
            candidate.sdpMid = value.get('sdpMid')
            candidate.sdpMLineIndex = value.get('sdpMLineIndex')
            if pc.remoteDescription is None:
                candidates.append(candidate)
            else:
                await pc.addIceCandidate(candidate)
        except Exception:
            log.exception('Unable to add ICE candidate')

    @sio.on('stream:stopped')
    async def stream_stopped(data):
        async with rtc_lock:
            if data['sessionId'] == session_id:
                await close_stream()

    def on_image(image):
        with image_lock:
            latest['image_at'] = time.monotonic()
            latest['image'] = image  # Latest only: do not accumulate camera latency.

    def control_loop():
        try:
            while not quit_event.is_set():
                throttle, brake, steer = controls.current()
                vehicle.apply_control(carla.VehicleControl(throttle=throttle, brake=brake, steer=steer))
                snapshot = world.get_snapshot()
                actor = snapshot.find(vehicle.id)
                if actor is None:
                    raise RuntimeError('CARLA vehicle disappeared')
                velocity = actor.get_velocity()
                telemetry = {'speed': 3.6 * math.sqrt(velocity.x**2 + velocity.y**2 + velocity.z**2),
                    'throttle': throttle, 'brake': brake, 'steer': steer,
                    'heading': actor.get_transform().rotation.yaw % 360,
                    'gear': str(vehicle.get_control().gear), 'frameId': snapshot.frame,
                    'simulationTimestamp': snapshot.timestamp.elapsed_seconds}
                with image_lock:
                    latest['telemetry'] = telemetry
                    latest['telemetry_at'] = time.monotonic()
                quit_event.wait(0.05)
        except Exception as exc:
            log.exception('CARLA control loop stopped')
            with image_lock:
                latest['error'] = str(exc)
            quit_event.set()
        finally:
            try:
                vehicle.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0))
            except Exception:
                log.exception('Could not apply final brake')

    def setup_carla():
        nonlocal vehicle, camera, worker, world
        client = carla.Client(args.host, args.port)
        client.set_timeout(10.0)
        log.info('CARLA client %s, server %s', client.get_client_version(), client.get_server_version())
        if client.get_client_version() != client.get_server_version():
            raise RuntimeError('CARLA client/server versions must match. Install the Python client matching your simulator.')
        world = client.get_world()
        if world.get_settings().synchronous_mode:
            raise RuntimeError('This standalone bridge expects an asynchronous CARLA world. Start a fresh simulator without another synchronous controller.')
        blueprint = world.get_blueprint_library().filter(args.vehicle)[0]
        blueprint.set_attribute('role_name', 'ghostdriver')
        spawn_points = world.get_map().get_spawn_points()
        if not spawn_points:
            raise RuntimeError('Map has no vehicle spawn points')
        for transform in spawn_points:
            vehicle = world.try_spawn_actor(blueprint, transform)
            if vehicle:
                break
        if vehicle is None:
            raise RuntimeError('No free spawn point')
        vehicle.set_autopilot(False)
        vehicle.apply_control(carla.VehicleControl(brake=1.0))
        camera_bp = world.get_blueprint_library().find('sensor.camera.rgb')
        for key, value in {'image_size_x': args.width, 'image_size_y': args.height, 'fov': 90, 'sensor_tick': 1/30}.items():
            camera_bp.set_attribute(key, str(value))
        camera = world.spawn_actor(camera_bp, carla.Transform(carla.Location(x=2.0, z=1.5)), attach_to=vehicle)
        camera.listen(on_image)
        worker = threading.Thread(target=control_loop, name='carla-controls', daemon=True)
        worker.start()

    async def publish_status():
        while True:
            with image_lock:
                telemetry = latest['telemetry']
                ready = (time.monotonic() - latest['image_at'] < 2
                         and time.monotonic() - latest['telemetry_at'] < 2
                         and not quit_event.is_set())
            if sio.connected:
                try:
                    await sio.emit('vehicle:status', {'ready': ready, 'controlsStopped': controls.is_latched()})
                    if telemetry and ready:
                        await sio.emit('vehicle:telemetry', telemetry)
                except socketio.exceptions.SocketIOError:
                    controls.stop()
            await asyncio.sleep(0.2)

    try:
        await sio.connect(args.backend, auth={'role': 'sender', 'token': args.token},
                          transports=['websocket'], retry=True, wait_timeout=20)
        status_task = asyncio.create_task(publish_status())
        try:
            setup_task = asyncio.create_task(asyncio.to_thread(setup_carla))
            await asyncio.shield(setup_task)
        except Exception as exc:
            log.error('CARLA setup: %s', exc)
            raise
        while not quit_event.is_set():
            await asyncio.sleep(0.2)
        raise RuntimeError(latest['error'] or 'CARLA worker stopped')
    finally:
        controls.stop()
        quit_event.set()
        # to_thread keeps running after cancellation. Wait for it before destroying
        # actors so Ctrl+C during startup cannot leave a late-spawned camera/car behind.
        if setup_task:
            await asyncio.gather(setup_task, return_exceptions=True)
        if status_task:
            status_task.cancel()
            await asyncio.gather(status_task, return_exceptions=True)
        if worker:
            await asyncio.to_thread(worker.join, 11)
        await close_stream()
        await sio.shutdown()
        if camera:
            camera.stop()
            camera.destroy()
        if vehicle:
            vehicle.destroy()
        log.info('Bridge closed; its camera and vehicle have been removed')


def main():
    # --help remains available without third-party packages.
    if '--help' not in __import__('sys').argv and '-h' not in __import__('sys').argv:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).with_name('.env'))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', default=os.getenv('BACKEND_URL', 'http://127.0.0.1:4000'))
    parser.add_argument('--host', default='127.0.0.1', help='CARLA server address')
    parser.add_argument('--port', type=int, default=2000)
    parser.add_argument('--name', default='CARLA vehicle')
    parser.add_argument('--vehicle', default='vehicle.tesla.model3', help='Blueprint filter')
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--height', type=int, default=360)
    args = parser.parse_args()
    args.token = os.getenv('SENDER_TOKEN', '')
    if len(args.token) < 32:
        parser.error('Set SENDER_TOKEN in carla-service/.env (at least 32 characters)')
    backend_url = urlparse(args.backend)
    if backend_url.username or backend_url.password or backend_url.query or backend_url.fragment:
        parser.error('BACKEND_URL must not contain credentials, query parameters or a fragment')
    if backend_url.scheme != 'https' and not (backend_url.scheme == 'http' and backend_url.hostname in ('localhost', '127.0.0.1')):
        parser.error('Remote BACKEND_URL must use HTTPS')
    if args.width <= 0 or args.height <= 0:
        parser.error('Image dimensions must be positive')
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    try:
        async def supervise():
            while True:
                try:
                    await run(args)
                except (ImportError, ModuleNotFoundError):
                    raise
                except Exception as exc:
                    # Do not log URLs, SDP or credential-bearing exception contents.
                    log.error('Bridge unavailable (%s). Braking; retrying in 5 seconds.', type(exc).__name__)
                    await asyncio.sleep(5)
        asyncio.run(supervise())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        log.error('%s', exc)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
