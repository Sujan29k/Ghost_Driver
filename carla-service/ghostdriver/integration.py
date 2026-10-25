"""
GhostDriver integration v2 - tele-operation latency demo (CARLA 0.9.15, Python 3.7).

Three panels (stacked vertically):
  LIVE       what the vehicle camera sees right now (YOLO + brake override run on this)
  DELAYED    what the operator sees after the network delay (--latency ms)
  PREDICTED  the delayed frame warped forward by the delay (operator-side compensation)

Run examples:
  python integration_v2.py --latency 200
  python integration_v2.py --latency 500 --center-only
  python integration_v2.py --latency 800 --damping 0.7 --max-disp 80

Notes:
  * Panels are stacked vertically so nothing gets cut off on any screen.
  * Press Q in the preview window to quit.
"""

import argparse
import collections
import queue
import random

import carla
import cv2
import numpy as np
from ultralytics import YOLO

FPS = 25
FIXED_DELTA = 1.0 / FPS
TARGET_CLASSES = ["car", "truck", "bus", "person", "bicycle", "motorcycle"]

PANEL_W = 640
PANEL_H = 300


def farneback_flow_to_prev(prev, cur):
    g_cur  = cv2.cvtColor(cur,  cv2.COLOR_BGR2GRAY)
    g_prev = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
    return cv2.calcOpticalFlowFarneback(
        g_cur, g_prev, None, pyr_scale=0.5, levels=3, winsize=15,
        iterations=3, poly_n=5, poly_sigma=1.2, flags=0)


def warp_forward(cur, flow, k, mode, damping, max_disp):
    h, w = cur.shape[:2]
    flow = flow.astype(np.float32)
    if max_disp > 0:
        mag  = np.sqrt((flow ** 2).sum(axis=-1, keepdims=True))
        flow = flow * np.minimum(1.0, (max_disp / float(k)) / np.maximum(mag, 1e-6))
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32),
                         np.arange(h, dtype=np.float32))
    if mode == "direct":
        return cv2.remap(cur,
                         gx + k * damping * flow[..., 0],
                         gy + k * damping * flow[..., 1],
                         cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    img = cur
    mx, my = gx + damping * flow[..., 0], gy + damping * flow[..., 1]
    for _ in range(k):
        img = cv2.remap(img, mx, my, cv2.INTER_LINEAR,
                        borderMode=cv2.BORDER_REPLICATE)
    return img


def psnr(a, b):
    mse = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return 100.0 if mse == 0 else float(10 * np.log10(255.0 ** 2 / mse))


def get_matching(q, frame, timeout=15.0):
    import time
    deadline = time.time() + timeout
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            raise RuntimeError("No camera image for frame %d" % frame)
        try:
            item = q.get(timeout=remaining)
        except queue.Empty:
            raise RuntimeError("No camera image for frame %d" % frame)
        if item.frame == frame:
            return item
        if item.frame > frame:
            raise RuntimeError("Camera frame ahead of tick")


def add_label(img, text, color=(0, 255, 0), y=None):
    if y is None:
        y = img.shape[0] - 10
    cv2.putText(img, text, (10, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)


def make_panel(img, label_text, label_color):
    """Resize to panel size and burn in the label at the bottom."""
    p = cv2.resize(img, (PANEL_W, PANEL_H))
    add_label(p, label_text, label_color)
    return p


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--host",       default="127.0.0.1")
    p.add_argument("--port",       type=int,   default=2000)
    p.add_argument("--tm-port",    type=int,   default=8000)
    p.add_argument("--weights",    default="yolov8n.pt")
    p.add_argument("--latency",    type=int,   default=500,
                   help="simulated network delay in ms (200 / 500 / 800)")
    p.add_argument("--warp",       choices=["direct", "stepwise"], default="stepwise")
    p.add_argument("--damping",    type=float, default=0.7)
    p.add_argument("--max-disp",   type=float, default=80.0)
    p.add_argument("--vehicles",   type=int,   default=30)
    p.add_argument("--walkers",    type=int,   default=30)
    p.add_argument("--threshold",  type=float, default=0.08,
                   help="box area / frame area fraction to trigger brake")
    p.add_argument("--center-only", action="store_true",
                   help="only brake for objects centred in the middle 50%% of the image")
    p.add_argument("--no-brake",   action="store_true")
    p.add_argument("--panel-w",    type=int,   default=640,
                   help="width of each panel in pixels")
    p.add_argument("--panel-h",    type=int,   default=300,
                   help="height of each panel in pixels")
    p.add_argument("--seed",       type=int,   default=2026)
    return p.parse_args()


def main():
    args = parse_args()
    global PANEL_W, PANEL_H
    PANEL_W = args.panel_w
    PANEL_H = args.panel_h

    random.seed(args.seed)
    k = max(1, int(round(args.latency / (FIXED_DELTA * 1000.0))))
    print("[INFO] latency %d ms = %d frames at %d FPS" % (args.latency, k, FPS))
    print("[INFO] panel %dx%d  window %dx%d (vertical stack)"
          % (PANEL_W, PANEL_H, PANEL_W, PANEL_H * 3))

    client = carla.Client(args.host, args.port)
    client.set_timeout(30.0)
    world  = client.get_world()
    tm     = client.get_trafficmanager(args.tm_port)
    original_settings = world.get_settings()

    actors, controllers = [], []
    camera = ego = None

    try:
        settings = world.get_settings()
        settings.synchronous_mode   = True
        settings.fixed_delta_seconds = FIXED_DELTA
        world.apply_settings(settings)
        tm.set_synchronous_mode(True)
        tm.set_random_device_seed(args.seed)
        world.set_weather(carla.WeatherParameters.ClearNoon)

        bp_lib       = world.get_blueprint_library()
        spawn_points = world.get_map().get_spawn_points()
        random.shuffle(spawn_points)

        # ego vehicle
        ego = world.try_spawn_actor(bp_lib.find("vehicle.tesla.model3"), spawn_points[0])
        if ego is None:
            raise RuntimeError("Could not spawn ego vehicle")
        ego.set_autopilot(True, args.tm_port)
        tm.ignore_lights_percentage(ego, 0)
        tm.ignore_signs_percentage(ego, 0)
        tm.vehicle_percentage_speed_difference(ego, -30)
        actors.append(ego)

        # traffic
        vehicle_bps = [b for b in bp_lib.filter("vehicle.*")
                       if int(b.get_attribute("number_of_wheels")) == 4]
        n = 0
        for sp in spawn_points[1:]:
            if n >= args.vehicles:
                break
            v = world.try_spawn_actor(random.choice(vehicle_bps), sp)
            if v is None:
                continue
            v.set_autopilot(True, args.tm_port)
            tm.update_vehicle_lights(v, True)
            actors.append(v)
            n += 1
        print("[INFO] traffic vehicles: %d" % n)

        # walkers
        walker_bps    = list(bp_lib.filter("walker.pedestrian.*"))
        controller_bp = bp_lib.find("controller.ai.walker")
        walkers = []
        for _ in range(args.walkers):
            loc = world.get_random_location_from_navigation()
            if loc is None:
                continue
            bp = random.choice(walker_bps)
            if bp.has_attribute("is_invincible"):
                bp.set_attribute("is_invincible", "true")
            w = world.try_spawn_actor(bp, carla.Transform(loc))
            if w is None:
                continue
            c = world.try_spawn_actor(controller_bp, carla.Transform(), attach_to=w)
            if c is None:
                w.destroy()
                continue
            walkers.append(w)
            controllers.append(c)
        world.tick()
        for c in controllers:
            c.start()
            tgt = world.get_random_location_from_navigation()
            if tgt is not None:
                c.go_to_location(tgt)
            c.set_max_speed(random.uniform(1.0, 1.8))
        actors.extend(walkers)
        print("[INFO] pedestrians: %d" % len(walkers))

        # camera
        cam_bp = bp_lib.find("sensor.camera.rgb")
        cam_bp.set_attribute("image_size_x", "640")
        cam_bp.set_attribute("image_size_y", "480")
        cam_bp.set_attribute("fov", "90")
        camera = world.spawn_actor(
            cam_bp, carla.Transform(carla.Location(x=2.0, z=1.5)), attach_to=ego)
        cam_q = queue.Queue()
        camera.listen(cam_q.put)

        model = YOLO(args.weights)
        print("[INFO] YOLO weights: %s  |  center-only: %s  |  threshold: %.2f"
              % (args.weights, args.center_only, args.threshold))

        # resizable window — vertical stack
        cv2.namedWindow("GhostDriver v2", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("GhostDriver v2", PANEL_W, PANEL_H * 3)

        buf          = collections.deque(maxlen=k + 2)
        brake_hold   = 0
        clear_count  = 0
        autopilot_on = True
        psnr_delayed, psnr_pred = [], []

        print("[INFO] running — press Q to quit")

        while True:
            frame_id = world.tick()
            img      = get_matching(cam_q, frame_id)
            arr      = np.frombuffer(img.raw_data, dtype=np.uint8).reshape(
                           (img.height, img.width, 4))
            live = arr[:, :, :3].copy()
            buf.append(live)
            h, w = live.shape[:2]

            # ---------- YOLO on live frame (vehicle side) ----------
            live_view = live.copy()
            brake_now = False
            results   = model(live, conf=0.4, verbose=False)

            for box in results[0].boxes:
                name = model.names[int(box.cls)]
                if name not in TARGET_CLASSES:
                    continue
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                prox = ((x2 - x1) * (y2 - y1)) / float(w * h)
                cx   = 0.5 * (x1 + x2) / w
                in_lane = (0.25 <= cx <= 0.75) if args.center_only else True
                danger  = prox > args.threshold and in_lane
                color   = (0, 0, 255) if danger else (0, 255, 0)
                if danger:
                    brake_now = True
                cv2.rectangle(live_view, (x1, y1), (x2, y2), color, 2)
                cv2.putText(live_view,
                            "%s %.2f" % (name, prox),
                            (x1, max(12, y1 - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

            # ---------- brake override ----------
            if not args.no_brake:
                if brake_now:
                    brake_hold  = 10
                    clear_count = 0
                    if autopilot_on:
                        ego.set_autopilot(False, args.tm_port)
                        autopilot_on = False
                elif brake_hold > 0:
                    brake_hold -= 1
                else:
                    clear_count += 1
                if not autopilot_on:
                    if brake_hold > 0 or brake_now:
                        ego.apply_control(
                            carla.VehicleControl(brake=1.0, throttle=0.0))
                    elif clear_count >= 10:
                        ego.set_autopilot(True, args.tm_port)
                        autopilot_on = True

            # speed label on live panel
            try:
                v     = ego.get_velocity()
                speed = 3.6 * float(np.sqrt(v.x**2 + v.y**2 + v.z**2))
            except Exception:
                speed = float("nan")
            add_label(live_view,
                      "LIVE (vehicle side) | %.0f km/h" % speed,
                      color=(255, 255, 255), y=25)

            if brake_now and not args.no_brake:
                cv2.rectangle(live_view, (0, 0), (w - 1, h - 1), (0, 0, 255), 6)
                cv2.putText(live_view, "BRAKE OVERRIDE", (140, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3,
                            cv2.LINE_AA)

            # ---------- delayed + predicted (operator side) ----------
            if len(buf) < k + 2:
                waiting = np.zeros_like(live)
                add_label(waiting,
                          "filling delay buffer %d/%d" % (len(buf), k + 2),
                          y=PANEL_H // 2)
                combined = np.vstack([
                    make_panel(live_view, "LIVE | YOLO + brake override", (255, 255, 255)),
                    make_panel(waiting,   "DELAYED — buffering ...",       (0, 200, 255)),
                    make_panel(waiting,   "PREDICTED — buffering ...",     (0, 255, 255)),
                ])
                cv2.imshow("GhostDriver v2", combined)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue

            delayed_prev, delayed = buf[0], buf[1]
            flow      = farneback_flow_to_prev(delayed_prev, delayed)
            predicted = warp_forward(delayed, flow, k,
                                     args.warp, args.damping, args.max_disp)

            psnr_delayed.append(psnr(delayed, live))
            psnr_pred.append(psnr(predicted, live))
            recent_d = np.mean(psnr_delayed[-50:])
            recent_p = np.mean(psnr_pred[-50:])

            combined = np.vstack([
                make_panel(live_view,
                           "LIVE | YOLO + brake | %.0f km/h" % speed,
                           (255, 255, 255)),
                make_panel(delayed.copy(),
                           "DELAYED %d ms (operator sees)  PSNR %.1f dB"
                           % (args.latency, recent_d),
                           (0, 200, 255)),
                make_panel(predicted.copy(),
                           "PREDICTED +%d ms  PSNR %.1f dB"
                           % (args.latency, recent_p),
                           (0, 255, 255)),
            ])

            cv2.imshow("GhostDriver v2", combined)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        if psnr_pred:
            print("[RESULT] mean PSNR  delayed %.2f dB  |  predicted %.2f dB"
                  % (np.mean(psnr_delayed), np.mean(psnr_pred)))

    finally:
        print("[INFO] cleaning up ...")
        cv2.destroyAllWindows()
        if camera is not None:
            try:
                camera.stop()
                camera.destroy()
            except Exception:
                pass
        for c in controllers:
            try:
                c.stop()
                c.destroy()
            except Exception:
                pass
        for a in actors:
            try:
                a.destroy()
            except Exception:
                pass
        try:
            tm.set_synchronous_mode(False)
            world.apply_settings(original_settings)
        except Exception as exc:
            print("[WARN] could not restore settings: %s" % exc)
        print("[INFO] done")


if __name__ == "__main__":
    main()