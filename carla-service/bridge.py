"""CARLA traffic, YOLO camera stream and remote controls for GhostDriver."""
import argparse
import asyncio
import logging
import math
import os
from pathlib import Path
from fractions import Fraction
from urllib.parse import urlparse
import threading
import queue
import time
from control_state import ControlState
from perception import DEFAULT_WEIGHTS
from prediction import DEFAULT_RAFT_WEIGHTS
from traffic import TrafficScene

log = logging.getLogger('ghostdriver')


async def run(args):
    # Keep --help usable before the optional dependencies are installed.
    import carla
    import aiohttp
    import certifi
    import numpy as np
    import ssl
    import socketio
    from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer, VideoStreamTrack
    from aiortc.sdp import candidate_from_sdp
    from av import VideoFrame

    vehicle = camera = None
    worker = None
    perception_worker = None
    scene = None
    research = None
    operation_worker = None
    operations = queue.Queue(maxsize=8)
    event_loop = asyncio.get_running_loop()
    research_enabled = getattr(args, "research", False)
    pipeline = None
    perception = None
    ai_enabled = getattr(args, 'ai', 'off') == 'yolo'
    if research_enabled and ai_enabled:
        from comparison import ComparisonPipeline
        pipeline = ComparisonPipeline(args.device, args.raft_weights, args.video_delay,
                                      args.prediction, args.view, args.show_reference,
                                      raft_iterations=getattr(args, 'raft_iterations', 12))
    quit_event = threading.Event()
    controls = ControlState()
    image_lock = threading.Lock()
    latest = {'image': None, 'image_at': 0, 'output': None, 'output_at': 0,
              'output_frame': None, 'ai': {'enabled': False}, 'comparison': None,
              'telemetry': None, 'telemetry_at': 0, 'error': None, 'phase': 'starting'}
    ice_servers = []
    status_task = None
    setup_task = None
    world = None
    # Some Python installations have no populated default CA file. Add the
    # maintained CA bundle while retaining OS/custom trust and TLS verification.
    tls = ssl.create_default_context()
    tls.load_verify_locations(cafile=certifi.where())
    http_session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=tls))
    sio = socketio.AsyncClient(reconnection=True, http_session=http_session)
    pc = None
    track = None
    session_id = None
    candidates = []
    rtc_lock = asyncio.Lock()
    registration_lock = asyncio.Lock()

    def set_phase(phase):
        with image_lock:
            latest['phase'] = phase

    class CameraTrack(VideoStreamTrack):
        async def recv(self):
            # Never manufacture placeholder frames or replay a stalled camera forever.
            while True:
                with image_lock:
                    image = latest['image']
                    pixels = latest['output'] if ai_enabled else None
                    frame_id = latest['output_frame'] if ai_enabled else (image.frame if image else None)
                    fresh = time.monotonic() - latest['output_at' if ai_enabled else 'image_at'] < 2
                    if pipeline:
                        fresh = fresh and pipeline.is_current(latest.get('output_details') or {})
                if image is not None and fresh and frame_id != getattr(self, 'last_frame', None):
                    break
                await asyncio.sleep(0.01)
            self.last_frame = frame_id
            if not ai_enabled:
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
        if pipeline:
            pipeline.history.clear()
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
            if pipeline:
                pipeline.history.clear()
            config = await sio.call('rtc:config', {}, timeout=10)
            if not config.get('success'):
                raise RuntimeError('Could not load authenticated ICE configuration')
            ice_servers = config['iceServers']
            result = await sio.call('vehicle:join', {'name': args.name, 'mode': 'carla', 'researchVersion': 1 if research_enabled else 0}, timeout=5)
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
        accepted = controls.accept(data)
        if research and accepted:
            research.recorder.record('control', {**data, 'mode': controls.snapshot()['mode']})
            if research.takeover and not controls.is_latched() and (data.get('manualInput') is True or any(data.get(k, 0) for k in ('throttle', 'steer'))):
                if not research.takeover.get('firstActionNs'):
                    research.takeover['firstActionNs'] = time.monotonic_ns()
                    research.recorder.record('takeover:first-manual-action', research.takeover)

    @sio.on('vehicle:supervise')
    async def supervise(_data):
        if session_id and sio.connected:
            controls.supervise()

    @sio.on('research:observation')
    async def observation(data):
        if research:
            research.recorder.record('operator:network', data)

    @sio.on('research:notice')
    async def notice(data):
        if research:
            research.recorder.record('takeover:notification-receipt', data)

    def operation_loop():
        while not quit_event.is_set():
            try:
                request, future = operations.get(timeout=.1)
            except queue.Empty:
                continue
            if future.cancelled():
                continue
            try:
                result = {'success': True, 'state': research.command(request)}
            except ValueError as error:
                result = {'success': False, 'message': str(error)}
            except Exception:
                log.exception('Research operation failed')
                controls.stop('Research operation failed')
                result = {'success': False, 'message': 'CARLA operation failed; inspect sender logs'}
            def finish(future=future, result=result):
                if not future.done():
                    future.set_result(result)
            event_loop.call_soon_threadsafe(finish)

    @sio.on('research:apply')
    async def research_apply(data):
        if not research or quit_event.is_set():
            return {'success': False, 'message': 'CARLA research controller is not ready'}
        future = event_loop.create_future()
        try:
            operations.put_nowait(({**data, 'expectedGeneration': controls.snapshot()['generation']}, future))
            return await asyncio.wait_for(future, 7)
        except (asyncio.TimeoutError, queue.Full):
            controls.stop('Research operation timed out')
            return {'success': False, 'message': 'Operation timed out; controls remain stopped'}

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
        if pipeline:
            from comparison import Observation
            pipeline.history.append(Observation(image.timestamp, image.frame, image, time.monotonic(), len(image.raw_data)))
        with image_lock:
            latest['image_at'] = time.monotonic()
            latest['image'] = image  # Latest only: do not accumulate camera latency.

    def perception_loop():
        last_frame = None
        try:
            while not quit_event.is_set():
                with image_lock:
                    image, captured_at = latest['image'], latest['image_at']
                if image is None or image.frame == last_frame:
                    quit_event.wait(0.01)
                    continue
                last_frame = image.frame
                pixels = np.frombuffer(image.raw_data, dtype=np.uint8).reshape(image.height, image.width, 4)[:, :, :3].copy()
                started = time.monotonic()
                output_frame = image.frame
                if pipeline:
                    settings = pipeline.configuration()
                    annotation = perception.process if settings['view'] == 'compare' and settings['method'] != 'off' else None
                    output, comparison, samples, metrics = pipeline.process(
                        annotate=annotation, evaluate=bool(research and research.recorder.active))
                    with image_lock:
                        latest['comparison'] = comparison
                    if output is None:
                        quit_event.wait(.02)
                        continue
                    captured_at = comparison['sourceCapturedAt']
                    output_frame = (comparison['epoch'], comparison['revision'], comparison['referenceFrame'])
                    if not pipeline.is_current(comparison):
                        continue
                    if research and research.recorder.active:
                        research.recorder.frame(comparison, samples)
                else:
                    output, metrics = perception.process(pixels, timestamp=image.timestamp)
                with image_lock:
                    latest.update(output=output, output_at=captured_at,
                                  output_frame=output_frame, ai=metrics)
                    if pipeline:
                        latest['output_details'] = comparison
                # Work on the newest camera frame next; never queue old frames.
                quit_event.wait(max(0, 1 / getattr(args, 'ai_fps', 30) - (time.monotonic() - started)))
        except Exception as exc:
            log.exception('YOLO processing stopped')
            with image_lock:
                latest['error'] = str(exc)
            controls.stop()
            quit_event.set()

    def control_loop():
        try:
            while not quit_event.is_set():
                with image_lock:
                    fresh = time.monotonic() - latest['output_at' if ai_enabled else 'image_at'] < 2
                    if pipeline:
                        fresh = fresh and pipeline.is_current(latest.get('output_details') or {})
                if not fresh and not controls.is_latched():
                    controls.stop('Required monitoring video unavailable')
                if research:
                    research.tick()
                    actual = vehicle.get_control()
                    throttle, brake, steer = actual.throttle, actual.brake, actual.steer
                else:
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
                if research:
                    telemetry['research'] = research.snapshot()
                    research.recorder.record('telemetry', telemetry)
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
                if research:
                    with research.actuation_lock:
                        research._disable_autopilot()
                vehicle.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0))
            except Exception:
                log.exception('Could not apply final brake')

    def setup_carla():
        nonlocal vehicle, camera, worker, world, scene, perception, perception_worker, research, operation_worker
        if ai_enabled:
            set_phase('loading-models')
            from perception import Perception
            log.info('Loading YOLO checkpoint: %s', args.weights)
            perception = Perception(args.weights, args.device, args.confidence, args.optical_flow if not pipeline else False,
                prediction='off' if pipeline else getattr(args, 'prediction', 'off'),
                prediction_ms=getattr(args, 'prediction_ms', 250),
                raft_weights=getattr(args, 'raft_weights', DEFAULT_RAFT_WEIGHTS),
                raft_iterations=getattr(args, 'raft_iterations', 12))
        if pipeline and pipeline.configuration()['method'] == 'raft' and pipeline.configuration()['view'] in ('compare', 'predicted'):
            from prediction import PredictionView
            log.info('Loading RAFT-Small comparison checkpoint: %s', args.raft_weights)
            pipeline.predictors['raft'] = PredictionView('raft', weights=args.raft_weights, device=args.device,
                                                        iterations=getattr(args, 'raft_iterations', 12))
        set_phase('connecting-carla')
        client = carla.Client(args.host, args.port)
        client.set_timeout(10.0)
        log.info('CARLA client %s, server %s', client.get_client_version(), client.get_server_version())
        from carla_compat import validate_versions
        validate_versions(client.get_client_version(), client.get_server_version(), research_enabled)
        world = client.get_world()
        if world.get_settings().synchronous_mode:
            raise RuntimeError('This standalone bridge expects an asynchronous CARLA world. Start a fresh simulator without another synchronous controller.')
        if getattr(world.get_settings(), 'no_rendering_mode', False):
            raise RuntimeError('Enable CARLA rendering for RGB camera output.')
        blueprints = world.get_blueprint_library().filter(args.vehicle)
        if not blueprints:
            raise ValueError(f'No vehicle blueprint matches {args.vehicle}')
        blueprint = blueprints[0]
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
        # Actor transforms are cached at ticks. Wait before locating nearby
        # traffic, otherwise a freshly spawned ego may still report (0, 0, 0).
        world.wait_for_tick(10.0)
        set_phase('spawning-traffic')
        scene = TrafficScene(world, carla, seed=getattr(args, 'seed', 2026))
        scene.spawn(client, vehicle, getattr(args, 'traffic', 0), getattr(args, 'bicycles', 0),
                    getattr(args, 'pedestrians', 0), getattr(args, 'tm_port', 8000))
        camera_bp = world.get_blueprint_library().find('sensor.camera.rgb')
        for key, value in {'image_size_x': args.width, 'image_size_y': args.height, 'fov': 90, 'sensor_tick': 1/30}.items():
            camera_bp.set_attribute(key, str(value))
        camera = world.spawn_actor(camera_bp, carla.Transform(carla.Location(x=2.0, z=1.5)), attach_to=vehicle)
        set_phase('waiting-camera')
        camera.listen(on_image)
        if research_enabled:
            from research import ResearchController
            import hashlib
            from importlib.metadata import version, PackageNotFoundError
            def checkpoint(path):
                path = Path(path)
                return {'name': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} if path.is_file() else {'name': path.name, 'available': False}
            versions = {}
            for package in ('numpy', 'opencv-python', 'torch', 'torchvision', 'ultralytics', 'aiortc'):
                try:
                    versions[package] = version(package)
                except PackageNotFoundError:
                    versions[package] = 'not installed'
            research = ResearchController(world, client, carla, vehicle, controls, pipeline, args.record_dir,
                args.tm_port, args.seed, args.direction_speed_limit,
                {'carlaClient': client.get_client_version(), 'carlaServer': client.get_server_version(),
                 'yolo': {**checkpoint(args.weights), 'classes': getattr(getattr(perception, 'model', None), 'names', None)},
                 'raft': {**checkpoint(args.raft_weights), 'iterations': getattr(args, 'raft_iterations', 12)}, 'packages': versions,
                 'senderSources': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in Path(__file__).parent.glob('*.py')},
                 'extrapolation': {'flow': 'backward delayed-to-previous', 'motionScale': .7, 'maxDisplacementPixels': 80},
                 'traffic': dict(scene.counts), 'trafficSeed': args.seed,
                 'camera': {'width': args.width, 'height': args.height, 'fov': 90}})
            research.attach_sensors()
            operation_worker = threading.Thread(target=operation_loop, name='research-operations', daemon=True)
            operation_worker.start()
        if ai_enabled:
            perception_worker = threading.Thread(target=perception_loop, name='yolo-inference', daemon=True)
            perception_worker.start()
        worker = threading.Thread(target=control_loop, name='carla-controls', daemon=True)
        worker.start()

    async def publish_status():
        while True:
            with image_lock:
                telemetry = latest['telemetry']
                ready = (time.monotonic() - latest['image_at'] < 2
                         and (not ai_enabled or time.monotonic() - latest['output_at'] < 2)
                         and time.monotonic() - latest['telemetry_at'] < 2
                         and not quit_event.is_set())
                if pipeline:
                    ready = ready and pipeline.is_current(latest.get('output_details') or {})
                phase = latest['phase']
                if ready:
                    latest['phase'] = phase = 'ready'
                elif phase == 'ready':
                    phase = 'camera-unavailable'
                if pipeline and not ready and time.monotonic() - latest['image_at'] < 2 and not quit_event.is_set():
                    phase = 'buffering-video'
                if telemetry:
                    telemetry = {**telemetry, 'perception': {**latest['ai'], 'fresh': ready},
                                 'traffic': dict(scene.counts) if scene else {},
                                 'comparison': pipeline.report(latest['comparison']) if pipeline else latest['comparison']}
            if sio.connected:
                try:
                    await sio.emit('vehicle:status', {'ready': ready, 'phase': phase, 'controlsStopped': controls.is_latched()})
                    if telemetry:
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
    except Exception:
        set_phase('error')
        if sio.connected:
            try:
                await sio.emit('vehicle:status', {'ready': False, 'phase': 'error', 'controlsStopped': True})
                # Let the error status reach the operator before closing signaling.
                await asyncio.sleep(0.5)
            except socketio.exceptions.SocketIOError:
                pass
        raise
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
        if operation_worker:
            await asyncio.to_thread(operation_worker.join)
        if worker:
            await asyncio.to_thread(worker.join, 11)
        if perception_worker:
            await asyncio.to_thread(perception_worker.join, 11)
        try:
            await close_stream()
            await sio.shutdown()
        finally:
            await http_session.close()
            try:
                if research:
                    try:
                        await asyncio.to_thread(research.close)
                    except Exception:
                        log.exception('Research cleanup failed')
                if camera:
                    camera.stop()
                    camera.destroy()
            finally:
                try:
                    if vehicle:
                        vehicle.destroy()
                finally:
                    if scene:
                        scene.close()
        log.info('Bridge closed; its camera, vehicle and background traffic have been removed')


def parse_args(argv=None, environ=None):
    env = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', default=env.get('BACKEND_URL', 'http://127.0.0.1:4000'))
    parser.add_argument('--host', default=env.get('CARLA_HOST', '127.0.0.1'), help='CARLA server address')
    parser.add_argument('--port', type=int, default=env.get('CARLA_PORT', '2000'))
    parser.add_argument('--name', default=env.get('VEHICLE_NAME', 'Friend CARLA'))
    parser.add_argument('--vehicle', default='vehicle.tesla.model3', help='Blueprint filter')
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--height', type=int, default=360)
    parser.add_argument('--ai', choices=['yolo', 'off'], default=env.get('AI_MODE', 'yolo'), help='YOLO annotations or raw camera')
    parser.add_argument('--weights', type=Path, default=DEFAULT_WEIGHTS, help='Local trained YOLO checkpoint')
    parser.add_argument('--device', default=env.get('AI_DEVICE', 'auto'), help='auto, cpu, or CUDA index such as 0')
    parser.add_argument('--confidence', type=float, default=0.4)
    parser.add_argument('--ai-fps', type=float, default=env.get('AI_FPS', '30'), help='Maximum inference frequency; actual FPS depends on compute and transport')
    parser.add_argument('--raft-iterations', type=int, default=env.get('RAFT_ITERATIONS', '12'), help='RAFT refinements (1-32); fewer can be faster but less accurate')
    parser.add_argument('--optical-flow', action='store_true', help='Add a side-by-side Farneback motion view')
    parser.add_argument('--prediction', choices=['off', 'raft', 'farneback'], default=env.get('PREDICTION', 'off'),
                        help='Optional estimated future view beside live YOLO video')
    parser.add_argument('--prediction-ms', type=int, default=env.get('PREDICTION_MS', '250'), help='Prediction horizon, not measured network latency')
    parser.add_argument('--raft-weights', type=Path, default=DEFAULT_RAFT_WEIGHTS)
    parser.add_argument('--traffic', type=int, default=env.get('TRAFFIC_CARS', '30'), help='Background cars requested; 0 disables')
    parser.add_argument('--bicycles', type=int, default=env.get('TRAFFIC_BICYCLES', '5'))
    parser.add_argument('--pedestrians', type=int, default=env.get('TRAFFIC_PEDESTRIANS', '20'))
    parser.add_argument('--tm-port', type=int, default=8000)
    parser.add_argument('--research', action=argparse.BooleanOptionalAction, default=env.get('RESEARCH_ENABLED', 'true').lower() == 'true')
    parser.add_argument('--video-delay', type=int, choices=[0, 100, 200, 500, 800], default=int(env.get('VIDEO_DELAY_MS', '200')))
    parser.add_argument('--view', choices=['compare', 'delayed', 'predicted', 'reference'], default=env.get('VIDEO_VIEW', 'compare'))
    parser.add_argument('--show-reference', action='store_true')
    parser.add_argument('--direction-speed-limit', type=float, default=float(env.get('DIRECTION_SPEED_LIMIT_KMH', '1')))
    parser.add_argument('--seed', type=int, default=int(env.get('RESEARCH_SEED', '2026')))
    parser.add_argument('--record-dir', type=Path, default=Path(__file__).with_name('recordings'))
    args = parser.parse_args(argv)
    if not 1 <= args.raft_iterations <= 32:
        parser.error('--raft-iterations must be between 1 and 32')
    if not 0 < args.direction_speed_limit <= 5 or not 0 <= args.seed <= 2147483647:
        parser.error('Direction limit must be in (0, 5] km/h and seed in [0, 2147483647]')
    if args.video_delay not in (0, 100, 200, 500, 800) or args.view not in ('compare', 'delayed', 'predicted', 'reference'):
        parser.error('Invalid video delay or display mode')
    args.token = env.get('SENDER_TOKEN', '')
    if len(args.token) < 32:
        parser.error('Set SENDER_TOKEN in carla-service/.env (at least 32 characters)')
    try:
        backend_url = urlparse(args.backend)
        backend_port = backend_url.port
    except ValueError:
        parser.error('BACKEND_URL must be a valid base URL with a valid port')
    if not backend_url.hostname or backend_url.path not in ('', '/') or backend_port == 0:
        parser.error('BACKEND_URL must be the backend base URL, without an API path')
    if backend_url.username or backend_url.password or backend_url.query or backend_url.fragment:
        parser.error('BACKEND_URL must not contain credentials, query parameters or a fragment')
    if backend_url.scheme != 'https' and not (backend_url.scheme == 'http' and backend_url.hostname in ('localhost', '127.0.0.1')):
        parser.error('Remote BACKEND_URL must use HTTPS')
    if args.width <= 0 or args.height <= 0:
        parser.error('Image dimensions must be positive')
    if not 1 <= args.port <= 65535 or not 1 <= args.tm_port <= 65535:
        parser.error('CARLA and traffic manager ports must be between 1 and 65535')
    if args.ai not in ('yolo', 'off') or args.prediction not in ('off', 'raft', 'farneback'):
        parser.error('AI_MODE must be yolo/off and PREDICTION must be off/raft/farneback')
    if not 0 < args.confidence <= 1 or not 0 < args.ai_fps <= 60:
        parser.error('Confidence must be in (0, 1] and AI FPS in (0, 60]')
    if any(not 0 <= count <= 200 for count in (args.traffic, args.bicycles, args.pedestrians)):
        parser.error('Traffic counts must be between 0 and 200')
    if args.optical_flow and args.ai == 'off':
        parser.error('--optical-flow requires --ai yolo')
    if args.prediction != 'off' and args.ai == 'off':
        parser.error('--prediction requires --ai yolo')
    if args.prediction != 'off' and args.optical_flow:
        parser.error('Choose --prediction or --optical-flow for the second video panel')
    if not 1 <= args.prediction_ms <= 800:
        parser.error('--prediction-ms must be between 1 and 800')
    return args


def main():
    # --help remains available without third-party packages.
    if '--help' not in __import__('sys').argv and '-h' not in __import__('sys').argv:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).with_name('.env'))
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    try:
        async def supervise():
            while True:
                try:
                    await run(args)
                except (ImportError, ModuleNotFoundError, FileNotFoundError):
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
