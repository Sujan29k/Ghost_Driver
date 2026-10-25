"""
GhostDriver - CARLA frame capture and streamer (Python 3.7 / .venv)

Connects to CARLA, captures RGB frames from the ego vehicle camera,
and sends them as raw JPEG bytes over a TCP socket to stream_server.py.

Run FIRST (before stream_server.py):
  .venv\Scripts\activate
  python carla_stream.py --latency 500

The script also accepts control commands from stream_server.py:
  w/s = throttle/brake  a/d = steer left/right  space = hand brake
"""

import argparse
import queue
import random
import socket
import struct
import threading
import time

import carla
import cv2
import numpy as np

FPS          = 25
FIXED_DELTA  = 1.0 / FPS
IMAGE_W      = 640
IMAGE_H      = 480
JPEG_QUALITY = 85
TCP_HOST     = "127.0.0.1"
TCP_PORT     = 5555


def speed_kmh(vehicle):
    try:
        v = vehicle.get_velocity()
        return float(np.sqrt(v.x**2 + v.y**2 + v.z**2) * 3.6)
    except Exception:
        return 0.0


def get_matching(q, frame, timeout=30.0):
    deadline = time.time() + timeout
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            raise RuntimeError("Timeout waiting for frame %d" % frame)
        try:
            item = q.get(timeout=remaining)
        except queue.Empty:
            raise RuntimeError("Timeout waiting for frame %d" % frame)
        if item.frame >= frame:
            return item


def send_frame(conn, frame_bgr, speed, latency):
    """Send one frame over TCP: [4-byte length][4-byte speed_x100][4-byte latency][JPEG bytes]"""
    ok, buf = cv2.imencode(".jpg", frame_bgr,
                           [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        return
    data  = buf.tobytes()
    spd_i = int(speed * 100)
    header = struct.pack(">III", len(data), spd_i, latency)
    try:
        conn.sendall(header + data)
    except Exception:
        raise ConnectionError("Client disconnected")


def recv_control(conn, ego, tm_port):
    """Background thread: receive single-byte control commands from stream_server."""
    THROTTLE = 0.0
    STEER    = 0.0
    BRAKE    = 0.0
    autopilot = True
    conn.settimeout(0.1)
    while True:
        try:
            data = conn.recv(1)
        except socket.timeout:
            continue
        except Exception:
            break
        if not data:
            break
        cmd = data.decode("utf-8", errors="ignore")
        if cmd == "w":
            THROTTLE = min(THROTTLE + 0.2, 1.0); BRAKE = 0.0
        elif cmd == "s":
            BRAKE = min(BRAKE + 0.3, 1.0); THROTTLE = 0.0
        elif cmd == "a":
            STEER = max(STEER - 0.15, -1.0)
        elif cmd == "d":
            STEER = min(STEER + 0.15, 1.0)
        elif cmd == " ":
            THROTTLE = 0.0; BRAKE = 1.0
        elif cmd == "p":
            autopilot = not autopilot
            try:
                ego.set_autopilot(autopilot, tm_port)
            except Exception:
                pass
            continue
        elif cmd == "0":
            THROTTLE = 0.0; STEER = 0.0; BRAKE = 0.0
        if not autopilot:
            try:
                ego.apply_control(carla.VehicleControl(
                    throttle=float(THROTTLE),
                    steer=float(STEER),
                    brake=float(BRAKE)))
            except Exception:
                pass
        # decay steer
        STEER *= 0.85
        if abs(STEER) < 0.01:
            STEER = 0.0


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--host",     default="127.0.0.1")
    p.add_argument("--port",     type=int, default=2000)
    p.add_argument("--tm-port",  type=int, default=8000)
    p.add_argument("--latency",  type=int, default=500,
                   help="simulated network delay in ms sent to stream_server")
    p.add_argument("--vehicles", type=int, default=30)
    p.add_argument("--walkers",  type=int, default=20)
    p.add_argument("--seed",     type=int, default=2026)
    p.add_argument("--tcp-port", type=int, default=TCP_PORT)
    return p.parse_args()


def main():
    args = parse_args()
    random.seed(args.seed)

    # ---- connect to CARLA first ----
    print("[CARLA] Connecting to CARLA simulator at %s:%d ..." % (args.host, args.port))
    client = carla.Client(args.host, args.port)
    client.set_timeout(30.0)
    world  = client.get_world()
    print("[CARLA] Connected to CARLA: %s" % client.get_server_version())

    tm     = client.get_trafficmanager(args.tm_port)
    original_settings = world.get_settings()

    ego = camera = None
    actors, controllers = [], []
    conn = srv = None

    try:
        settings = world.get_settings()
        settings.synchronous_mode    = True
        settings.fixed_delta_seconds = FIXED_DELTA
        world.apply_settings(settings)
        tm.set_synchronous_mode(True)
        tm.set_random_device_seed(args.seed)
        world.set_weather(carla.WeatherParameters.ClearNoon)

        bp_lib       = world.get_blueprint_library()
        spawn_points = world.get_map().get_spawn_points()
        random.shuffle(spawn_points)

        # ego
        ego = world.try_spawn_actor(
            bp_lib.find("vehicle.tesla.model3"), spawn_points[0])
        if ego is None:
            raise RuntimeError("Could not spawn ego vehicle")
        ego.set_autopilot(True, args.tm_port)
        tm.vehicle_percentage_speed_difference(ego, -20)
        actors.append(ego)

        # traffic
        vehicle_bps = [b for b in bp_lib.filter("vehicle.*")
                       if int(b.get_attribute("number_of_wheels")) == 4]
        n = 0
        for sp in spawn_points[1:]:
            if n >= args.vehicles: break
            v = world.try_spawn_actor(random.choice(vehicle_bps), sp)
            if v is None: continue
            v.set_autopilot(True, args.tm_port)
            actors.append(v); n += 1
        print("[CARLA] traffic: %d vehicles" % n)

        # walkers
        walker_bps    = list(bp_lib.filter("walker.pedestrian.*"))
        controller_bp = bp_lib.find("controller.ai.walker")
        for _ in range(args.walkers):
            loc = world.get_random_location_from_navigation()
            if loc is None: continue
            bp = random.choice(walker_bps)
            if bp.has_attribute("is_invincible"):
                bp.set_attribute("is_invincible", "true")
            w = world.try_spawn_actor(bp, carla.Transform(loc))
            if w is None: continue
            c = world.try_spawn_actor(controller_bp, carla.Transform(), attach_to=w)
            if c is None: w.destroy(); continue
            actors.append(w); controllers.append(c)
        world.tick()
        for c in controllers:
            c.start()
            tgt = world.get_random_location_from_navigation()
            if tgt: c.go_to_location(tgt)
            c.set_max_speed(random.uniform(1.0, 1.8))
        print("[CARLA] pedestrians: %d" % len(controllers))

        # camera
        cam_bp = bp_lib.find("sensor.camera.rgb")
        cam_bp.set_attribute("image_size_x", str(IMAGE_W))
        cam_bp.set_attribute("image_size_y", str(IMAGE_H))
        cam_bp.set_attribute("fov", "90")
        camera = world.spawn_actor(
            cam_bp, carla.Transform(carla.Location(x=2.0, z=1.5)), attach_to=ego)
        cam_q = queue.Queue()
        camera.listen(cam_q.put)

        # tick once so camera registers in synchronous mode
        world.tick()
        # drain any queued frames
        try:
            while True:
                cam_q.get_nowait()
        except Exception:
            pass

        # ---- wait for stream_server to connect ----
        print("[CARLA] Waiting for stream_server.py to connect on port %d ..." % args.tcp_port)
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((TCP_HOST, args.tcp_port))
        srv.listen(1)
        conn, addr = srv.accept()
        print("[CARLA] stream_server connected from %s" % str(addr))

        # start control receiver thread
        ctrl_thread = threading.Thread(
            target=recv_control, args=(conn, ego, args.tm_port), daemon=True)
        ctrl_thread.start()

        print("[CARLA] Streaming frames — press Ctrl+C to stop")
        while True:
            world.tick()
            try:
                img = cam_q.get(timeout=2.0)
            except queue.Empty:
                print("[CARLA] waiting for camera frame ...")
                continue
            # drain extra frames so we stay real-time
            while not cam_q.empty():
                try:
                    img = cam_q.get_nowait()
                except Exception:
                    break
            arr = np.frombuffer(img.raw_data, dtype=np.uint8).reshape(
                (img.height, img.width, 4))
            bgr = arr[:, :, :3].copy()
            spd = speed_kmh(ego)
            if conn is not None:
                try:
                    send_frame(conn, bgr, spd, args.latency)
                except ConnectionError:
                    print("[CARLA] stream_server disconnected — waiting for reconnect")
                    try: conn.close()
                    except Exception: pass
                    conn = None
            if conn is None:
                # non-blocking accept — keep ticking CARLA while waiting
                srv.settimeout(0.0)
                try:
                    conn, addr = srv.accept()
                    print("[CARLA] Reconnected from %s" % str(addr))
                    ctrl_thread = threading.Thread(
                        target=recv_control, args=(conn, ego, args.tm_port), daemon=True)
                    ctrl_thread.start()
                except socket.error:
                    pass  # no client yet, keep ticking
                finally:
                    srv.settimeout(None)

    except KeyboardInterrupt:
        print("\n[CARLA] Stopped by user.")
    finally:
        print("[CARLA] Cleaning up ...")
        try: conn.close()
        except Exception: pass
        try: srv.close()
        except Exception: pass
        if camera:
            try: camera.stop(); camera.destroy()
            except Exception: pass
        for c in controllers:
            try: c.stop(); c.destroy()
            except Exception: pass
        for a in actors:
            try: a.destroy()
            except Exception: pass
        try:
            tm.set_synchronous_mode(False)
            world.apply_settings(original_settings)
        except Exception: pass
        print("[CARLA] Done.")


if __name__ == "__main__":
    main()