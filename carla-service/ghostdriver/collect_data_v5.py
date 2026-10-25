"""
GhostDriver CARLA 0.9.15 - data collector v5 (v4 + depth map and camera pose per frame).

New in v5: sensor.camera.depth saved as 16-bit PNG (centimetres) in <condition>/depth/, and the
4x4 camera pose matrix (rows 0-2 as m00..m23) in metadata.csv. Needed by evaluate_geometric.py.
Optical-flow ground truth is now off by default (--flow-every 0).

What changed compared with v3:
  * Lossless PNG frames (no JPEG noise in flow / PSNR / SSIM).
  * Strict frame matching: every saved image has image.frame == world.tick() frame.
  * No sensor_tick (it can skip ticks in synchronous mode).
  * Output is map-aware: <output>/<map>/<condition>/ (Town03 can never overwrite Town10).
  * Refuses to overwrite existing data unless --overwrite; --resume continues a partial set.
  * segment_id column: frames inside one segment are strictly consecutive (use it to build
    frame pairs / t+5, t+12, t+20 targets without crossing gaps or resume points).
  * Frames where the ego is nearly stopped are skipped (and start a new segment).
  * Optional ground-truth optical flow (sensor.camera.optical_flow), saved every N frames.
  * Headlights managed by the Traffic Manager (needed for night / fog conditions).
  * Red-light running disabled for the ego, TM seeded, per-condition collision log.

Run examples:
  python collect_data_v4.py --map Town03 --conditions heavy_rain --resume
  python collect_data_v4.py --map Town03 --conditions fog_night storm
  python collect_data_v4.py --map Town10HD_Opt --frames 5000

Notes:
  * Start CARLA first. This script owns world.tick(); do not run another ticking client.
  * Validation here means file integrity and frame order, not model accuracy.
"""

import argparse
import csv
import queue
import random
import time
import traceback
from pathlib import Path

import carla
import cv2
import numpy as np

# ----------------------------- FIXED SETTINGS -----------------------------
IMAGE_WIDTH = 640
IMAGE_HEIGHT = 480
FPS = 25
FIXED_DELTA = 1.0 / FPS
CAMERA_FOV = 90
CAMERA_TRANSFORM = carla.Transform(carla.Location(x=2.0, z=1.5))

FRAME_TIMEOUT_SECONDS = 15.0
WARMUP_FRAMES = 50
WEATHER_SETTLE_FRAMES = 25
STUCK_SECONDS = 20          # ego below min speed this long -> teleport to a new spawn point
VALIDATE_EVERY = 50         # re-read every Nth PNG from disk to verify it decodes
PNG_COMPRESSION = 3         # lossless; 0 = fastest/biggest, 9 = slowest/smallest

WEATHER_CONDITIONS = {
    "clear_traffic": carla.WeatherParameters.ClearNoon,
    "heavy_rain": carla.WeatherParameters.HardRainNoon,
    "fog_night": carla.WeatherParameters(
        cloudiness=80, precipitation=0, sun_altitude_angle=-15,
        fog_density=75, fog_distance=35, fog_falloff=1.5,
        wetness=30, wind_intensity=25),
    "storm": carla.WeatherParameters(
        cloudiness=100, precipitation=100, precipitation_deposits=100,
        wind_intensity=100, fog_density=50, wetness=100),
    "dust_sunset": carla.WeatherParameters(
        cloudiness=60, precipitation=0, sun_altitude_angle=5,
        fog_density=30, wind_intensity=80),
    "night_rain": carla.WeatherParameters(
        cloudiness=100, precipitation=80, sun_altitude_angle=-90,
        fog_density=20, wetness=100, wind_intensity=50),
}

POSE_COLS = ["m%d%d" % (r, c) for r in range(3) for c in range(4)]
CSV_FIELDS = [
    "filename", "segment_id", "frame_id", "simulation_timestamp", "condition",
    "ego_speed_kmh", "image_width", "image_height", "collision_count", "flow_file",
    "depth_file",
] + POSE_COLS


# ----------------------------- HELPERS -----------------------------
def parse_args():
    p = argparse.ArgumentParser(description="GhostDriver CARLA data collector v4")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=2000)
    p.add_argument("--tm-port", type=int, default=8000)
    p.add_argument("--map", default="Town03", help="e.g. Town03, Town10HD_Opt")
    p.add_argument("--output", default="dataset_v5")
    p.add_argument("--conditions", nargs="+", default=list(WEATHER_CONDITIONS),
                   choices=list(WEATHER_CONDITIONS), help="which conditions to collect")
    p.add_argument("--frames", type=int, default=5000, help="saved frames per condition")
    p.add_argument("--resume", action="store_true",
                   help="continue a partial condition (counts rows in metadata.csv)")
    p.add_argument("--overwrite", action="store_true",
                   help="delete nothing, but start metadata.csv again from scratch")
    p.add_argument("--min-speed", type=float, default=3.0,
                   help="skip frames when ego speed is below this (km/h)")
    p.add_argument("--flow-every", type=int, default=0,
                   help="save ground-truth optical flow every N saved frames (0 = off)")
    p.add_argument("--vehicles", type=int, default=120)
    p.add_argument("--walkers", type=int, default=80)
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--preview", action="store_true", help="show an OpenCV preview window")
    return p.parse_args()


def safe_destroy(actor):
    if actor is not None:
        try:
            actor.destroy()
        except Exception as exc:
            print(f"[WARN] Could not destroy actor: {exc}")


def speed_kmh(vehicle):
    try:
        v = vehicle.get_velocity()
        return float(np.sqrt(v.x * v.x + v.y * v.y + v.z * v.z) * 3.6)
    except Exception:
        return float("nan")


def drain(q):
    while True:
        try:
            q.get_nowait()
        except queue.Empty:
            return


def get_matching(q, frame, what):
    """Return the sensor item whose .frame equals `frame`; discard older (stale) items."""
    deadline = time.time() + FRAME_TIMEOUT_SECONDS
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            raise TimeoutError(f"No {what} data for frame {frame}.")
        try:
            item = q.get(timeout=remaining)
        except queue.Empty:
            raise TimeoutError(f"No {what} data for frame {frame}.")
        if item.frame == frame:
            return item
        if item.frame > frame:
            raise RuntimeError(f"{what} frame {item.frame} is ahead of tick frame {frame}.")
        # item.frame < frame: stale, discard and keep waiting


def make_sensor_queue(sensor):
    q = queue.Queue()
    sensor.listen(q.put)
    return q


def spawn_camera(world, bp_lib, kind, ego):
    bp = bp_lib.find(kind)
    bp.set_attribute("image_size_x", str(IMAGE_WIDTH))
    bp.set_attribute("image_size_y", str(IMAGE_HEIGHT))
    bp.set_attribute("fov", str(CAMERA_FOV))
    if kind == "sensor.camera.rgb":
        bp.set_attribute("enable_postprocess_effects", "true")
    # No sensor_tick: in synchronous mode the sensor fires on every world tick.
    return world.spawn_actor(bp, CAMERA_TRANSFORM, attach_to=ego)


def spawn_traffic(world, bp_lib, tm, spawn_points, count, tm_port):
    vehicles = []
    blueprints = [b for b in bp_lib.filter("vehicle.*")
                  if int(b.get_attribute("number_of_wheels")) == 4]
    for transform in spawn_points:
        if len(vehicles) >= count:
            break
        actor = world.try_spawn_actor(random.choice(blueprints), transform)
        if actor is None:
            continue
        actor.set_autopilot(True, tm_port)
        tm.distance_to_leading_vehicle(actor, random.uniform(2.5, 5.0))
        tm.vehicle_percentage_speed_difference(actor, random.uniform(-5.0, 20.0))
        tm.update_vehicle_lights(actor, True)   # TM switches lights on in dark weather
        vehicles.append(actor)
    print(f"[INFO] Traffic vehicles spawned: {len(vehicles)}/{count}")
    return vehicles


def spawn_walkers(world, bp_lib, count):
    walkers, controllers = [], []
    walker_bps = list(bp_lib.filter("walker.pedestrian.*"))
    controller_bp = bp_lib.find("controller.ai.walker")
    for _ in range(count):
        location = world.get_random_location_from_navigation()
        if location is None:
            continue
        bp = random.choice(walker_bps)
        if bp.has_attribute("is_invincible"):
            bp.set_attribute("is_invincible", "true")   # no dead pedestrians in the data
        walker = world.try_spawn_actor(bp, carla.Transform(location))
        if walker is None:
            continue
        controller = world.try_spawn_actor(controller_bp, carla.Transform(), attach_to=walker)
        if controller is None:
            safe_destroy(walker)
            continue
        walkers.append(walker)
        controllers.append(controller)
    world.tick()
    for controller in controllers:
        try:
            controller.start()
            target = world.get_random_location_from_navigation()
            if target is not None:
                controller.go_to_location(target)
            controller.set_max_speed(random.uniform(1.0, 1.8))
        except Exception as exc:
            print(f"[WARN] Walker controller setup failed: {exc}")
    print(f"[INFO] Pedestrians spawned: {len(walkers)}/{count}")
    return walkers, controllers


def read_existing(manifest_path):
    """Return (rows_saved, last_segment_id) from an existing metadata.csv."""
    saved, last_segment = 0, -1
    if manifest_path.exists():
        with manifest_path.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                saved += 1
                try:
                    last_segment = max(last_segment, int(row["segment_id"]))
                except (KeyError, ValueError):
                    pass
    return saved, last_segment


def flush_collisions(collision_events, path):
    if not collision_events:
        return
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["condition", "frame", "other_actor_id", "other_actor_type"])
        if new_file:
            writer.writeheader()
        writer.writerows(collision_events)
    collision_events.clear()


# ----------------------------- MAIN -----------------------------
def main():
    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)

    client = carla.Client(args.host, args.port)
    client.set_timeout(30.0)

    world = client.get_world()
    if not world.get_map().name.endswith(args.map):
        print(f"[INFO] Loading map {args.map} ...")
        world = client.load_world(args.map)
    map_name = world.get_map().name.split("/")[-1]

    tm = client.get_trafficmanager(args.tm_port)
    original_settings = world.get_settings()
    original_weather = world.get_weather()

    ego = rgb_cam = flow_cam = depth_cam = collision_sensor = None
    traffic, walkers, controllers = [], [], []
    collision_events = []
    current_collision_path = None

    try:
        settings = world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = FIXED_DELTA
        settings.no_rendering_mode = False
        world.apply_settings(settings)
        tm.set_synchronous_mode(True)
        tm.set_random_device_seed(args.seed)

        bp_lib = world.get_blueprint_library()
        spawn_points = world.get_map().get_spawn_points()
        if len(spawn_points) < 2:
            raise RuntimeError("Map has too few spawn points.")
        random.shuffle(spawn_points)

        ego = world.try_spawn_actor(bp_lib.find("vehicle.tesla.model3"), spawn_points[0])
        if ego is None:
            raise RuntimeError("Could not spawn ego vehicle.")
        ego.set_autopilot(True, args.tm_port)
        tm.ignore_lights_percentage(ego, 0)          # obey red lights: fewer crashes / stops
        tm.ignore_signs_percentage(ego, 0)
        tm.auto_lane_change(ego, True)
        tm.random_left_lanechange_percentage(ego, 20)
        tm.random_right_lanechange_percentage(ego, 20)
        tm.update_vehicle_lights(ego, True)

        traffic = spawn_traffic(world, bp_lib, tm, spawn_points[1:], args.vehicles, args.tm_port)
        walkers, controllers = spawn_walkers(world, bp_lib, args.walkers)

        rgb_cam = spawn_camera(world, bp_lib, "sensor.camera.rgb", ego)
        rgb_q = make_sensor_queue(rgb_cam)

        flow_q = None
        if args.flow_every > 0:
            flow_cam = spawn_camera(world, bp_lib, "sensor.camera.optical_flow", ego)
            flow_q = make_sensor_queue(flow_cam)

        current_condition = [""]
        collision_counter = [0]
        depth_cam = spawn_camera(world, bp_lib, "sensor.camera.depth", ego)
        depth_q = make_sensor_queue(depth_cam)

        collision_sensor = world.spawn_actor(
            bp_lib.find("sensor.other.collision"), carla.Transform(), attach_to=ego)
        def on_collision(e):
            collision_counter[0] += 1
            collision_events.append({
            "condition": current_condition[0],
            "frame": int(e.frame),
            "other_actor_id": int(e.other_actor.id) if e.other_actor else -1,
            "other_actor_type": e.other_actor.type_id if e.other_actor else "",
            })

        collision_sensor.listen(on_collision)

        print(f"[INFO] Map: {map_name} | step {FIXED_DELTA:.4f}s ({FPS} FPS) | "
              f"flow GT: {'every %d frames' % args.flow_every if flow_q else 'off'}")

        def tick_and_drain(n):
            for _ in range(n):
                frame = world.tick()
                get_matching(rgb_q, frame, "RGB")
                get_matching(depth_q, frame, "depth")
                if flow_q is not None:
                    get_matching(flow_q, frame, "flow")

        print("[INFO] Warming up ...")
        tick_and_drain(WARMUP_FRAMES)

        for condition in args.conditions:
            print(f"\n[INFO] Condition: {condition}")
            current_condition[0] = condition
            world.set_weather(WEATHER_CONDITIONS[condition])
            tick_and_drain(WEATHER_SETTLE_FRAMES)
            drain(rgb_q)
            drain(depth_q)
            if flow_q is not None:
                drain(flow_q)

            condition_dir = Path(args.output) / map_name / condition
            rgb_dir = condition_dir / "rgb"
            depth_dir = condition_dir / "depth"
            depth_dir.mkdir(parents=True, exist_ok=True)
            flow_dir = condition_dir / "flow"
            rgb_dir.mkdir(parents=True, exist_ok=True)
            if flow_q is not None:
                flow_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = condition_dir / "metadata.csv"
            current_collision_path = condition_dir / "collisions.csv"

            existing, last_segment = read_existing(manifest_path)
            if existing and not (args.resume or args.overwrite):
                print(f"[SKIP] {manifest_path} already has {existing} rows. "
                      f"Use --resume to continue or --overwrite to restart it.")
                continue
            if args.overwrite:
                existing, last_segment = 0, -1
                if manifest_path.exists():
                    manifest_path.rename(manifest_path.with_suffix(".csv.bak"))
            if existing >= args.frames:
                print(f"[SKIP] {condition} already complete ({existing}/{args.frames}).")
                continue

            saved = existing
            segment_id = last_segment + 1          # a resume or new condition never joins old frames
            need_new_segment = False
            stopped_ticks = 0
            ticks = 0
            max_ticks = (args.frames - existing) * 20
            collision_counter[0] = 0
            started = time.time()
            start_saved = saved
            write_header = not manifest_path.exists()

            with manifest_path.open("a", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
                if write_header:
                    writer.writeheader()

                while saved < args.frames:
                    ticks += 1
                    if ticks > max_ticks:
                        raise RuntimeError(
                            f"{condition}: too many ticks with the ego barely moving "
                            f"({saved}/{args.frames} saved). Check the traffic / spawn.")

                    frame = world.tick()
                    rgb = get_matching(rgb_q, frame, "RGB")
                    depth = get_matching(depth_q, frame, "depth")
                    pose = rgb_cam.get_transform().get_matrix()
                    flow = get_matching(flow_q, frame, "flow") if flow_q is not None else None
                    speed = speed_kmh(ego)

                    if not speed > args.min_speed:     # also catches NaN
                        stopped_ticks += 1
                        need_new_segment = True
                        if stopped_ticks >= STUCK_SECONDS * FPS:
                            ego.set_transform(random.choice(spawn_points))
                            stopped_ticks = 0
                            print("[INFO] Ego stuck, moved to a new spawn point.")
                        continue
                    stopped_ticks = 0
                    if need_new_segment:
                        segment_id += 1
                        need_new_segment = False

                    # --- RGB (lossless PNG) ---
                    bgra = np.frombuffer(rgb.raw_data, dtype=np.uint8).reshape(
                        (rgb.height, rgb.width, 4))
                    bgr = bgra[:, :, :3]
                    filename = f"s{segment_id:03d}_f{rgb.frame:08d}.png"
                    path = rgb_dir / filename
                    ok = cv2.imwrite(str(path), bgr,
                                     [cv2.IMWRITE_PNG_COMPRESSION, PNG_COMPRESSION])
                    if not ok or not path.exists() or path.stat().st_size == 0:
                        raise IOError(f"Failed to write {path}")
                    if saved % VALIDATE_EVERY == 0:
                        check = cv2.imread(str(path), cv2.IMREAD_COLOR)
                        if check is None or check.shape[:2] != (IMAGE_HEIGHT, IMAGE_WIDTH):
                            raise IOError(f"Saved image failed validation: {path}")

                    # --- depth: CARLA encodes metres in R + G*256 + B*65536 (scaled to 1000 m) ---
                    dbgra = np.frombuffer(depth.raw_data, dtype=np.uint8).reshape(
                        (depth.height, depth.width, 4)).astype(np.float64)
                    meters = (dbgra[:, :, 2] + dbgra[:, :, 1] * 256.0 + dbgra[:, :, 0] * 65536.0) \
                        / (256.0 ** 3 - 1.0) * 1000.0
                    depth_cm = np.clip(meters * 100.0, 0, 65535).astype(np.uint16)
                    depth_file = filename
                    if not cv2.imwrite(str(depth_dir / depth_file), depth_cm):
                        raise IOError("Failed to write depth " + depth_file)

                    # --- ground-truth optical flow (raw sensor values, float16 .npy) ---
                    flow_file = ""
                    if flow is not None and saved % args.flow_every == 0:
                        arr = np.frombuffer(flow.raw_data, dtype=np.float32).reshape(
                            (flow.height, flow.width, 2))
                        flow_file = f"s{segment_id:03d}_f{rgb.frame:08d}.npy"
                        np.save(flow_dir / flow_file, arr.astype(np.float16))

                    row = {
                        "filename": filename,
                        "segment_id": segment_id,
                        "frame_id": int(rgb.frame),
                        "simulation_timestamp": f"{rgb.timestamp:.6f}",
                        "condition": condition,
                        "ego_speed_kmh": f"{speed:.3f}",
                        "image_width": rgb.width,
                        "image_height": rgb.height,
                        "collision_count": collision_counter[0],
                        "flow_file": flow_file,
                        "depth_file": depth_file,
                    }
                    for r_i in range(3):
                        for c_i in range(4):
                            row["m%d%d" % (r_i, c_i)] = "%.6f" % pose[r_i][c_i]
                    writer.writerow(row)
                    csv_file.flush()
                    saved += 1

                    if saved % 100 == 0:
                        elapsed = max(time.time() - started, 1e-6)
                        print(f"[{condition}] {saved}/{args.frames} | "
                              f"{(saved - start_saved) / elapsed:.2f} saved FPS | "
                              f"segments {segment_id + 1} | ego {speed:.1f} km/h")
                        flush_collisions(collision_events, current_collision_path)

                    if args.preview and saved % 5 == 0:
                        view = bgr.copy()
                        cv2.putText(view, f"{condition} {saved}/{args.frames}", (10, 25),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                        cv2.imshow("GhostDriver v4", view)
                        if cv2.waitKey(1) & 0xFF == ord("q"):
                            print(f"[WARN] Skipped {condition} at {saved} frames (Q pressed).")
                            break

            flush_collisions(collision_events, current_collision_path)
            status = "OK" if saved >= args.frames else "INCOMPLETE"
            print(f"[{status}] {condition}: {saved}/{args.frames} frames, "
                  f"{segment_id + 1} segments, manifest={manifest_path}")

        print("\n[COMPLETE] Collection finished. Inspect each condition's metadata.csv.")

    except KeyboardInterrupt:
        print("\n[STOP] Interrupted by user. Progress is saved; use --resume to continue.")
    except Exception as exc:
        print(f"\n[ERROR] {exc}")
        traceback.print_exc()
        raise
    finally:
        print("[INFO] Cleaning up ...")
        try:
            if current_collision_path is not None:
                flush_collisions(collision_events, current_collision_path)
        except Exception as exc:
            print(f"[WARN] Could not write collisions: {exc}")
        for sensor in (rgb_cam, flow_cam, depth_cam, collision_sensor):
            if sensor is not None:
                try:
                    sensor.stop()
                except Exception:
                    pass
                safe_destroy(sensor)
        for controller in controllers:
            try:
                controller.stop()
            except Exception:
                pass
            safe_destroy(controller)
        for actor in walkers + traffic + ([ego] if ego is not None else []):
            safe_destroy(actor)
        try:
            tm.set_synchronous_mode(False)
        except Exception:
            pass
        try:
            world.apply_settings(original_settings)
            world.set_weather(original_weather)
        except Exception as exc:
            print(f"[WARN] Could not fully restore CARLA settings: {exc}")
        if args.preview:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass
        print("[INFO] Cleanup finished.")


if __name__ == "__main__":
    main()