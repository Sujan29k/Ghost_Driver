#!/usr/bin/env python3
"""Bridge CARLA vehicle control, telemetry, and camera frames to Ghost Driver."""

import argparse
from collections import deque
import json
import math
from pathlib import Path
from queue import Empty, Full, Queue
import struct
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
import urllib.request

try:
    import socketio
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"python-socketio is required: {exc}")

try:
    import carla
except Exception:  # pragma: no cover
    carla = None

try:
    import cv2
    import numpy as np
except Exception:  # pragma: no cover
    cv2 = None
    np = None

try:
    from ultralytics import YOLO
except Exception as exc:  # pragma: no cover
    YOLO = None
    YOLO_IMPORT_ERROR = str(exc)
else:
    YOLO_IMPORT_ERROR = None

DEFAULT_WEIGHTS = (
    Path(__file__).resolve().parent
    / "yolov8n_coco128-5"
    / "weights"
    / "best.pt"
)


def farneback_flow_to_prev(previous: Any, current: Any) -> Any:
    current_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
    previous_gray = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
    return cv2.calcOpticalFlowFarneback(
        current_gray,
        previous_gray,
        None,
        0.5,
        3,
        15,
        3,
        5,
        1.2,
        0,
    )


def warp_forward(current: Any, flow: Any, steps: int, damping: float, max_displacement: float) -> Any:
    height, width = current.shape[:2]
    flow = flow.astype(np.float32)
    if max_displacement > 0:
        magnitude = np.sqrt((flow ** 2).sum(axis=-1, keepdims=True))
        flow *= np.minimum(
            1.0,
            (max_displacement / float(steps)) / np.maximum(magnitude, 1e-6),
        )

    grid_x, grid_y = np.meshgrid(
        np.arange(width, dtype=np.float32),
        np.arange(height, dtype=np.float32),
    )
    map_x = grid_x + damping * flow[..., 0]
    map_y = grid_y + damping * flow[..., 1]
    predicted = current
    for _ in range(steps):
        predicted = cv2.remap(
            predicted,
            map_x,
            map_y,
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
    return predicted


def structural_similarity(first: Any, second: Any) -> float:
    first = first.astype(np.float32)
    second = second.astype(np.float32)
    mu_first = cv2.GaussianBlur(first, (11, 11), 1.5)
    mu_second = cv2.GaussianBlur(second, (11, 11), 1.5)
    sigma_first = cv2.GaussianBlur(first * first, (11, 11), 1.5) - mu_first * mu_first
    sigma_second = cv2.GaussianBlur(second * second, (11, 11), 1.5) - mu_second * mu_second
    covariance = cv2.GaussianBlur(first * second, (11, 11), 1.5) - mu_first * mu_second
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    score = ((2 * mu_first * mu_second + c1) * (2 * covariance + c2)) / (
        (mu_first ** 2 + mu_second ** 2 + c1) * (sigma_first + sigma_second + c2)
    )
    return float(np.mean(score))


class MjpegHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split('?', 1)[0]
        frame_paths = {
            '/stream.mjpg': 'latest_frame',
            '/delayed.mjpg': 'delayed_frame',
            '/predicted.mjpg': 'predicted_frame',
        }
        if path not in frame_paths:
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header('Cache-Control', 'no-cache, no-store')
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        previous_frame = None
        frame_name = frame_paths[path]
        try:
            while True:
                with self.server.gateway.frame_lock:
                    frame = getattr(self.server.gateway, frame_name)
                    if frame is None and frame_name == 'predicted_frame':
                        frame = self.server.gateway.latest_frame
                if frame is None or frame is previous_frame:
                    time.sleep(0.05)
                    continue

                self.wfile.write(
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n'
                    + f'Content-Length: {len(frame)}\r\n\r\n'.encode('ascii')
                    + frame
                    + b'\r\n'
                )
                self.wfile.flush()
                previous_frame = frame
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def log_message(self, format: str, *args: Any) -> None:
        return


class CarlaGateway:
    def __init__(self, host: str = "http://localhost:4000", name: str = "CARLA-Gateway"):
        self.host = host
        self.name = name
        self.sio = socketio.Client()
        self.vehicle = None
        self.camera = None
        self.world = None
        self.latest_frame = None
        self.delayed_frame = None
        self.predicted_frame = None
        self.frame_lock = threading.Lock()
        self.frame_history = deque(maxlen=24)
        self.camera_server = None
        self.yolo_model = None
        self.yolo_imgsz = 416
        self.yolo_conf = 0.25
        self.detections = []
        self.inference_ms = 0.0
        self.prediction_ready = False
        self.latency_ms = 500
        self.camera_delay_ms = 250
        self.control_delay_ms = 250
        self.prediction_horizon_ms = 250
        self.camera_tick_seconds = 0.1
        self.prediction_damping = 0.7
        self.prediction_max_displacement = 80.0
        self.prediction_method = 'RAFT-Small'
        self.prediction_metrics = {}
        self.inference_queue = Queue(maxsize=1)
        self.inference_stop = threading.Event()
        self.inference_thread = None
        self.prediction_queue = Queue(maxsize=1)
        self.prediction_thread = None
        self.control_queue = Queue()
        self.control_thread = None
        self.raft_url = 'http://127.0.0.1:5002/predict'
        self.raft_health_url = 'http://127.0.0.1:5002/health'
        self.raft_process = None
        self.raft_ready = False

        @self.sio.on("connect")
        def on_connect():
            print(f"[gateway] connected to {host}")
            self.sio.emit("vehicle:join", {"name": self.name})
            self.emit_perception_status()

        @self.sio.on("latency:configure")
        def on_latency_configure(data: Dict[str, Any]) -> None:
            try:
                latency_ms = int(data.get('latencyMs', 500))
            except (AttributeError, TypeError, ValueError):
                return
            if latency_ms not in (0, 200, 500, 800):
                return
            with self.frame_lock:
                self.latency_ms = latency_ms
                self.camera_delay_ms = latency_ms // 2
                self.control_delay_ms = latency_ms - self.camera_delay_ms
                self.prediction_horizon_ms = self.camera_delay_ms
                self.prediction_ready = False
                self.prediction_metrics = {}
                self.predicted_frame = None
                self.delayed_frame = None
                self.frame_history.clear()
            print(f"[gateway] injected latency: {latency_ms}ms")
            self.emit_perception_status()

        @self.sio.on("control:apply")
        def on_control(data: Dict[str, Any]):
            if not isinstance(data, dict):
                return
            throttle = float(data.get("throttle", 0.0) or 0.0)
            brake = float(data.get("brake", 0.0) or 0.0)
            steer = float(data.get("steer", 0.0) or 0.0)
            with self.frame_lock:
                apply_at = time.monotonic() + self.control_delay_ms / 1000.0
            self.control_queue.put(
                (apply_at, throttle, brake, steer, bool(data.get('emergency')))
            )

    def connect_carla(self, host: str = "127.0.0.1", port: int = 2000) -> None:
        if carla is None:
            print("[gateway] CARLA Python API is not available; running in telemetry-only mode.")
            return
        client = carla.Client(host, port)
        client.set_timeout(10.0)
        self.world = client.get_world()
        blueprint = self.world.get_blueprint_library().find("vehicle.tesla.model3")
        existing_vehicle = next(
            (
                actor
                for actor in self.world.get_actors().filter("vehicle.*")
                if actor.attributes.get("role_name") == self.name
            ),
            None,
        )
        if existing_vehicle is not None:
            self.vehicle = existing_vehicle
            print(f"[gateway] reusing CARLA vehicle {self.vehicle.id}")
            return

        blueprint.set_attribute("role_name", self.name)
        spawn_points = self.world.get_map().get_spawn_points()
        if not spawn_points:
            raise RuntimeError("CARLA has no spawn points")
        self.vehicle = self.world.try_spawn_actor(blueprint, spawn_points[0])
        if self.vehicle is None:
            print("[gateway] could not spawn vehicle in CARLA")
            return
        print("[gateway] connected to CARLA and spawned vehicle")

    def load_yolo(self, weights: str, imgsz: int = 416, confidence: float = 0.25) -> None:
        if YOLO is None:
            print(f"[gateway] YOLO unavailable: {YOLO_IMPORT_ERROR}")
            return
        try:
            self.yolo_model = YOLO(weights)
            self.yolo_imgsz = imgsz
            self.yolo_conf = confidence
            self.inference_thread = threading.Thread(target=self._run_inference, daemon=True)
            self.inference_thread.start()
            print(f"[gateway] YOLO loaded: {weights} (CPU, imgsz={imgsz})")
        except Exception as exc:
            self.yolo_model = None
            print(f"[gateway] YOLO model load failed: {exc}")

    def emit_perception_status(self) -> None:
        if not self.sio.connected:
            return
        with self.frame_lock:
            perception = {
                "modelLoaded": self.yolo_model is not None,
                "detections": list(self.detections),
                "inferenceMs": self.inference_ms,
                "predictionReady": self.prediction_ready,
                "predictionHorizonMs": self.prediction_horizon_ms,
                "latencyMs": self.latency_ms,
                "cameraDelayMs": self.camera_delay_ms,
                "controlDelayMs": self.control_delay_ms,
                "predictionMethod": self.prediction_method,
                "predictionMetrics": dict(self.prediction_metrics),
            }
        self.sio.emit("vehicle:perception", perception)

    def start_raft_worker(self) -> None:
        try:
            with urllib.request.urlopen(self.raft_health_url, timeout=1.0) as response:
                if json.loads(response.read().decode('utf-8')).get('ready'):
                    self.raft_ready = True
                    print('[gateway] using existing RAFT worker')
                    return
        except Exception:
            pass

        project_root = Path(__file__).resolve().parents[2]
        python = project_root / 'raft-env' / 'Scripts' / 'python.exe'
        worker = Path(__file__).resolve().parent / 'raft_worker.py'
        if not python.is_file() or not worker.is_file():
            print('[gateway] RAFT environment unavailable; Farneback fallback enabled')
            self.prediction_method = 'Farneback'
            return

        try:
            self.raft_process = subprocess.Popen(
                [str(python), str(worker), '--host', '127.0.0.1', '--port', '5002'],
                cwd=str(project_root),
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
        except Exception as exc:
            print(f'[gateway] could not start RAFT worker: {exc}')
            self.prediction_method = 'Farneback'
            return

        deadline = time.time() + 45.0
        while time.time() < deadline and self.raft_process.poll() is None:
            try:
                with urllib.request.urlopen(self.raft_health_url, timeout=1.0) as response:
                    status = json.loads(response.read().decode('utf-8'))
                    if status.get('ready'):
                        self.raft_ready = True
                        print(f"[gateway] RAFT worker ready ({status.get('device')})")
                        return
            except Exception:
                time.sleep(0.25)

        print('[gateway] RAFT worker did not become ready; Farneback fallback enabled')
        self.prediction_method = 'Farneback'

    def start_camera(self, port: int = 5001) -> None:
        if self.vehicle is None or carla is None or cv2 is None or np is None:
            print("[gateway] camera unavailable; CARLA/OpenCV is not ready")
            return

        blueprint = self.world.get_blueprint_library().find("sensor.camera.rgb")
        blueprint.set_attribute("image_size_x", "640")
        blueprint.set_attribute("image_size_y", "360")
        blueprint.set_attribute("fov", "90")
        blueprint.set_attribute("sensor_tick", str(self.camera_tick_seconds))
        transform = carla.Transform(
            carla.Location(x=1.5, z=1.7),
            carla.Rotation(pitch=-5.0),
        )
        self.camera = self.world.try_spawn_actor(blueprint, transform, attach_to=self.vehicle)
        if self.camera is None:
            print("[gateway] could not spawn CARLA RGB camera")
            return

        self.camera.listen(self._on_camera_image)
        self.camera_server = ThreadingHTTPServer(("0.0.0.0", port), MjpegHandler)
        self.camera_server.gateway = self
        threading.Thread(target=self.camera_server.serve_forever, daemon=True).start()
        self.prediction_thread = threading.Thread(target=self._run_prediction, daemon=True)
        self.prediction_thread.start()
        print(f"[gateway] CARLA camera stream at http://localhost:{port}/stream.mjpg")

    def _on_camera_image(self, image: Any) -> None:
        pixels = np.frombuffer(image.raw_data, dtype=np.uint8).reshape((image.height, image.width, 4))
        bgr = cv2.cvtColor(pixels, cv2.COLOR_BGRA2BGR)
        timestamp = time.monotonic()
        with self.frame_lock:
            self.frame_history.append((timestamp, bgr.copy()))
            detections = list(self.detections)
            model_loaded = self.yolo_model is not None
            latency_ms = self.camera_delay_ms
            history = list(self.frame_history)

        preview = bgr.copy()
        for detection in detections:
            x1, y1, x2, y2 = detection["bbox"]
            cv2.rectangle(preview, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"{detection['class']} {detection['confidence']:.2f}"
            cv2.putText(
                preview,
                label,
                (x1, max(18, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )
        status = f"YOLO LIVE | {len(detections)} detections" if model_loaded else "YOLO OFFLINE"
        cv2.putText(preview, status, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

        encoded, jpeg = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if encoded:
            with self.frame_lock:
                self.latest_frame = jpeg.tobytes()

        target_time = timestamp - latency_ms / 1000.0
        eligible_frames = [entry for entry in history if entry[0] <= target_time]
        if len(eligible_frames) >= 2:
            previous = eligible_frames[-2][1]
            delayed = eligible_frames[-1][1]
        else:
            previous, delayed = None, bgr

        delayed_preview = delayed.copy()
        delayed_label = (
            f'DELAYED +{latency_ms}ms'
            if previous is not None
            else f'BUFFERING {latency_ms}ms'
        )
        cv2.putText(
            delayed_preview,
            delayed_label,
            (10, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 200, 255),
            2,
            cv2.LINE_AA,
        )
        delayed_encoded, delayed_jpeg = cv2.imencode(
            '.jpg', delayed_preview, [cv2.IMWRITE_JPEG_QUALITY, 75]
        )
        if delayed_encoded:
            with self.frame_lock:
                self.delayed_frame = delayed_jpeg.tobytes()

        if previous is not None:
            task = (previous.copy(), delayed.copy(), bgr.copy(), latency_ms)
            try:
                self.prediction_queue.put_nowait(task)
            except Full:
                try:
                    self.prediction_queue.get_nowait()
                except Empty:
                    pass
                try:
                    self.prediction_queue.put_nowait(task)
                except Full:
                    pass

        if self.yolo_model is not None:
            try:
                self.inference_queue.put_nowait(bgr)
            except Full:
                try:
                    self.inference_queue.get_nowait()
                except Empty:
                    pass
                try:
                    self.inference_queue.put_nowait(bgr)
                except Full:
                    pass

    def _run_prediction(self) -> None:
        while not self.inference_stop.is_set():
            try:
                previous, delayed, live, latency_ms = self.prediction_queue.get(timeout=0.25)
            except Empty:
                continue

            started = time.perf_counter()
            try:
                if latency_ms <= 0:
                    farneback_prediction = delayed.copy()
                else:
                    farneback_flow = farneback_flow_to_prev(previous, delayed)
                    farneback_steps = max(
                        1,
                        int(round(latency_ms / (self.camera_tick_seconds * 1000))),
                    )
                    farneback_prediction = warp_forward(
                        delayed,
                        farneback_flow,
                        farneback_steps,
                        self.prediction_damping,
                        self.prediction_max_displacement,
                    )

                if latency_ms <= 0:
                    predicted = delayed.copy()
                    inference_ms = 0.0
                    method = 'RAFT-Small'
                elif self.raft_ready:
                    previous_ok, previous_jpeg = cv2.imencode('.jpg', previous)
                    delayed_ok, delayed_jpeg = cv2.imencode('.jpg', delayed)
                    if not previous_ok or not delayed_ok:
                        raise RuntimeError('Could not encode delayed frame pair')
                    payload = previous_jpeg.tobytes() + delayed_jpeg.tobytes()
                    request = urllib.request.Request(
                        self.raft_url,
                        data=payload,
                        headers={
                            'Content-Type': 'application/octet-stream',
                            'X-Previous-Size': str(len(previous_jpeg)),
                            'X-Latency-Ms': str(latency_ms),
                        },
                        method='POST',
                    )
                    with urllib.request.urlopen(request, timeout=8.0) as response:
                        output = np.frombuffer(response.read(), dtype=np.uint8)
                        predicted = cv2.imdecode(output, cv2.IMREAD_COLOR)
                        inference_ms = float(response.headers.get('X-Inference-Ms', 0.0))
                    if predicted is None:
                        raise RuntimeError('RAFT worker returned an invalid frame')
                    method = 'RAFT-Small'
                else:
                    flow = farneback_flow_to_prev(previous, delayed)
                    steps = max(1, int(round(latency_ms / (self.camera_tick_seconds * 1000))))
                    predicted = warp_forward(
                        delayed,
                        flow,
                        steps,
                        self.prediction_damping,
                        self.prediction_max_displacement,
                    )
                    inference_ms = (time.perf_counter() - started) * 1000.0
                    method = 'Farneback'

                cv2.putText(
                    predicted,
                    f'{method} +{latency_ms}ms',
                    (10, 24),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
                predicted_jpeg_ok, predicted_jpeg = cv2.imencode(
                    '.jpg', predicted, [cv2.IMWRITE_JPEG_QUALITY, 75]
                )
                if not predicted_jpeg_ok:
                    raise RuntimeError('Could not encode predicted frame')

                delayed_psnr = cv2.PSNR(live, delayed)
                farneback_psnr = cv2.PSNR(live, farneback_prediction)
                predicted_psnr = cv2.PSNR(live, predicted)
                metrics = {
                    'delayedPsnr': round(delayed_psnr, 2) if math.isfinite(delayed_psnr) else 100.0,
                    'farnebackPsnr': round(farneback_psnr, 2) if math.isfinite(farneback_psnr) else 100.0,
                    'predictedPsnr': round(predicted_psnr, 2) if math.isfinite(predicted_psnr) else 100.0,
                    'raftPsnr': round(predicted_psnr, 2) if method == 'RAFT-Small' and math.isfinite(predicted_psnr) else None,
                    'delayedSsim': structural_similarity(live, delayed),
                    'farnebackSsim': structural_similarity(live, farneback_prediction),
                    'predictedSsim': structural_similarity(live, predicted),
                    'raftSsim': structural_similarity(live, predicted) if method == 'RAFT-Small' else None,
                }
                with self.frame_lock:
                    self.predicted_frame = predicted_jpeg.tobytes()
                    self.prediction_ready = True
                    self.prediction_method = method
                    self.prediction_metrics = metrics
                    self.inference_ms = inference_ms
                    self.prediction_horizon_ms = latency_ms
                self.emit_perception_status()
            except Exception as exc:
                print(f'[gateway] prediction failed: {exc}')
                if self.raft_ready:
                    self.raft_ready = False
                    self.prediction_method = 'Farneback'

    def _run_inference(self) -> None:
        while not self.inference_stop.is_set():
            try:
                frame = self.inference_queue.get(timeout=0.25)
            except Empty:
                continue

            started = time.perf_counter()
            try:
                result = self.yolo_model.predict(
                    frame,
                    imgsz=self.yolo_imgsz,
                    conf=self.yolo_conf,
                    device="cpu",
                    verbose=False,
                )[0]
                detections = []
                for box in result.boxes:
                    class_id = int(box.cls[0])
                    x1, y1, x2, y2 = [int(value) for value in box.xyxy[0].tolist()]
                    detections.append(
                        {
                            "class": result.names[class_id],
                            "confidence": round(float(box.conf[0]), 3),
                            "bbox": [x1, y1, x2, y2],
                        }
                    )

                inference_ms = round((time.perf_counter() - started) * 1000, 1)
                with self.frame_lock:
                    self.detections = detections
                    self.inference_ms = inference_ms
                self.emit_perception_status()
            except Exception as exc:
                print(f"[gateway] YOLO inference failed: {exc}")
                self.yolo_model = None
                self.emit_perception_status()

    def _run_controls(self) -> None:
        while not self.inference_stop.is_set():
            try:
                apply_at, throttle, brake, steer, emergency = self.control_queue.get(timeout=0.25)
            except Empty:
                continue

            remaining = apply_at - time.monotonic()
            if remaining > 0 and self.inference_stop.wait(remaining):
                return
            if self.vehicle is None or carla is None:
                continue
            try:
                self.vehicle.apply_control(
                    carla.VehicleControl(
                        throttle=throttle,
                        brake=brake,
                        steer=steer,
                    )
                )
                print(
                    f"[gateway] applied control: throttle={throttle} brake={brake} "
                    f"steer={steer} emergency={emergency}"
                )
            except Exception as exc:  # pragma: no cover
                print(f"[gateway] apply_control failed: {exc}")

    def emit_telemetry(self) -> None:
        if self.vehicle is None or carla is None:
            payload = {
                "speed": 0.0,
                "throttle": 0.0,
                "brake": 0.0,
                "steer": 0.0,
                "gear": "P",
                "heading": 0.0,
                "location": {"lat": 48.8566, "lon": 2.3522, "altitude": 0.0},
                "carlaConnected": False,
                "timestamp": int(time.time() * 1000),
            }
        else:
            velocity = self.vehicle.get_velocity()
            speed = 3.6 * ((velocity.x ** 2 + velocity.y ** 2 + velocity.z ** 2) ** 0.5)
            transform = self.vehicle.get_transform()
            payload = {
                "speed": round(float(speed), 1),
                "throttle": 0.0,
                "brake": 0.0,
                "steer": 0.0,
                "gear": "D",
                "heading": round(float(transform.rotation.yaw), 1),
                "location": {
                    "lat": round(float(transform.location.x), 4),
                    "lon": round(float(transform.location.y), 4),
                    "altitude": round(float(transform.location.z), 4),
                },
                "carlaConnected": True,
                "timestamp": int(time.time() * 1000),
            }
        self.sio.emit("vehicle:telemetry", payload)

    def close(self) -> None:
        self.inference_stop.set()
        for worker in (self.inference_thread, self.prediction_thread):
            if worker is not None:
                worker.join(timeout=2.0)
        if self.control_thread is not None:
            self.control_thread.join(timeout=2.0)
        if self.sio.connected:
            self.sio.disconnect()
        if self.camera_server is not None:
            self.camera_server.shutdown()
            self.camera_server.server_close()
        if self.camera is not None:
            self.camera.stop()
            self.camera.destroy()
        if self.vehicle is not None and self.vehicle.is_alive:
            self.vehicle.destroy()
        if self.raft_process is not None and self.raft_process.poll() is None:
            self.raft_process.terminate()
            try:
                self.raft_process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self.raft_process.kill()

    def run(
        self,
        rate_hz: int = 10,
        carla_host: str = "127.0.0.1",
        carla_port: int = 2000,
        camera_port: int = 5001,
        weights: str = str(DEFAULT_WEIGHTS),
        yolo_imgsz: int = 416,
        yolo_conf: float = 0.25,
        latency_rtt_ms: int = 500,
    ) -> None:
        try:
            self.latency_ms = latency_rtt_ms
            self.camera_delay_ms = latency_rtt_ms // 2
            self.control_delay_ms = latency_rtt_ms - self.camera_delay_ms
            self.prediction_horizon_ms = self.camera_delay_ms
            self.start_raft_worker()
            self.load_yolo(weights, yolo_imgsz, yolo_conf)
            self.connect_carla(carla_host, carla_port)
            self.start_camera(camera_port)
            self.control_thread = threading.Thread(target=self._run_controls, daemon=True)
            self.control_thread.start()
            self.sio.connect(self.host)
            sleep_seconds = 1.0 / max(1, rate_hz)
            while True:
                if self.sio.connected:
                    self.emit_telemetry()
                time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            print("[gateway] stopping")
        finally:
            self.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ghost Driver CARLA gateway")
    parser.add_argument("--host", default="http://localhost:4000", help="Node backend URL")
    parser.add_argument("--name", default="CARLA-Gateway", help="Vehicle name")
    parser.add_argument("--carla-host", default="127.0.0.1", help="CARLA Host")
    parser.add_argument("--carla-port", type=int, default=2000, help="CARLA port")
    parser.add_argument("--camera-port", type=int, default=5001, help="MJPEG camera port")
    parser.add_argument("--weights", default=str(DEFAULT_WEIGHTS), help="YOLO weights path")
    parser.add_argument("--yolo-imgsz", type=int, default=416, help="YOLO inference image size")
    parser.add_argument("--yolo-conf", type=float, default=0.25, help="YOLO confidence threshold")
    parser.add_argument(
        "--latency-rtt-ms",
        type=int,
        choices=(0, 200, 500, 800),
        default=500,
        help="Injected round-trip latency scenario",
    )
    parser.add_argument("--rate", type=int, default=10, help="Telemetry rate in Hz")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    gateway = CarlaGateway(args.host, args.name)
    gateway.run(
        args.rate,
        args.carla_host,
        args.carla_port,
        args.camera_port,
        args.weights,
        args.yolo_imgsz,
        args.yolo_conf,
        args.latency_rtt_ms,
    )
