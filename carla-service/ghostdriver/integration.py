import carla
import cv2
import numpy as np
import time
import random
import queue
from ultralytics import YOLO

# ── CONNECT TO CARLA ──────────────────────────────────────────
client = carla.Client('localhost', 2000)
client.set_timeout(30.0)
world = client.get_world()
print("✅ Connected:", world.get_map().name)

# ── TRAFFIC MANAGER SETUP ─────────────────────────────────────
tm = client.get_trafficmanager(8000)
tm.set_global_distance_to_leading_vehicle(1.5)
tm.set_synchronous_mode(False)
tm.global_percentage_speed_difference(-30)

world.set_weather(carla.WeatherParameters.ClearNoon)

# ── LOAD YOLO MODEL ──────────────────────────────────────────
model = YOLO('yolov8n_coco128-5/weights/best.pt')
print("✅ YOLOv8 loaded")

bp_lib = world.get_blueprint_library()
spawn_points = world.get_map().get_spawn_points()
spectator = world.get_spectator()

# ── SPAWN EGO VEHICLE ─────────────────────────────────────────
vehicle_bp = bp_lib.filter('vehicle.tesla.model3')[0]
vehicle = world.spawn_actor(vehicle_bp, spawn_points[0])
vehicle.set_autopilot(True, 8000)
tm.ignore_lights_percentage(vehicle, 100)
tm.ignore_signs_percentage(vehicle, 100)
tm.vehicle_percentage_speed_difference(vehicle, -50)
print("✅ Ego vehicle spawned")
time.sleep(2)

# ── SPAWN TRAFFIC VEHICLES ────────────────────────────────────
traffic = []
for i in range(5, 35):
    try:
        v_bp = random.choice(bp_lib.filter('vehicle.*'))
        v = world.spawn_actor(v_bp, spawn_points[i])
        v.set_autopilot(True, 8000)
        tm.ignore_lights_percentage(v, 100)
        tm.ignore_signs_percentage(v, 100)
        tm.vehicle_percentage_speed_difference(v, -20)
        traffic.append(v)
    except:
        pass
print(f"✅ {len(traffic)} traffic vehicles spawned")

# ── SPAWN BICYCLES ────────────────────────────────────────────
bicycles = []
bike_bps = (bp_lib.filter('vehicle.bh.crossbike') or
            bp_lib.filter('vehicle.gazelle.omafiets') or
            bp_lib.filter('vehicle.*bike*'))

for i in range(35, 45):
    try:
        if bike_bps:
            b = world.spawn_actor(random.choice(bike_bps), spawn_points[i])
            b.set_autopilot(True, 8000)
            tm.ignore_lights_percentage(b, 100)
            bicycles.append(b)
    except:
        pass
print(f"✅ {len(bicycles)} bicycles spawned")

# ── SPAWN PEDESTRIANS ─────────────────────────────────────────
walkers = []
walker_controllers = []
walker_controller_bp = bp_lib.find('controller.ai.walker')
walker_bps = bp_lib.filter('walker.pedestrian.*')

for _ in range(50):
    try:
        walker_bp = random.choice(walker_bps)
        loc = world.get_random_location_from_navigation()
        if loc is None:
            continue
        walker = world.spawn_actor(walker_bp, carla.Transform(loc))
        walkers.append(walker)
        controller = world.spawn_actor(
            walker_controller_bp, carla.Transform(), walker)
        walker_controllers.append(controller)
    except:
        pass

world.wait_for_tick()

for controller in walker_controllers:
    try:
        controller.start()
        controller.go_to_location(world.get_random_location_from_navigation())
        controller.set_max_speed(random.uniform(1.0, 2.5))
    except:
        pass
print(f"✅ {len(walkers)} pedestrians spawned")

# ── CAMERA ────────────────────────────────────────────────────
camera_bp = bp_lib.find('sensor.camera.rgb')
camera_bp.set_attribute('image_size_x', '640')
camera_bp.set_attribute('image_size_y', '480')
camera_bp.set_attribute('fov', '90')
camera = world.spawn_actor(
    camera_bp,
    carla.Transform(carla.Location(x=2.0, z=1.5)),
    attach_to=vehicle
)
print("✅ Camera attached")

# ── SHARED STATE ──────────────────────────────────────────────
frame_queue = queue.Queue(maxsize=2)
prev_gray = [None]
brake_active = [False]

def camera_callback(image):
    array = np.frombuffer(image.raw_data, dtype=np.uint8)
    array = array.reshape((image.height, image.width, 4))
    bgr = array[:, :, :3].copy()
    if not frame_queue.full():
        frame_queue.put(bgr)

camera.listen(camera_callback)

print("\n🚗 GhostDriver Running — Press Q to quit\n")

while True:
    if frame_queue.empty():
        time.sleep(0.01)
        continue

    frame = frame_queue.get()

    # ── SPECTATOR FOLLOWS VEHICLE ──────────────────────────────
    try:
        t = vehicle.get_transform()
        spectator.set_transform(carla.Transform(
            t.location + carla.Location(z=50),
            carla.Rotation(pitch=-90)
        ))
    except:
        break

    # ── OPTICAL FLOW ──────────────────────────────────────────
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    predicted_frame = frame.copy()

    if prev_gray[0] is not None:
        flow = cv2.calcOpticalFlowFarneback(
            prev_gray[0], gray, None,
            pyr_scale=0.5, levels=3, winsize=15,
            iterations=3, poly_n=5, poly_sigma=1.2, flags=0
        )
        h, w = frame.shape[:2]
        flow_map = np.zeros_like(flow)
        flow_map[:, :, 0] = np.arange(w)
        flow_map[:, :, 1] = np.arange(h)[:, None]
        flow_map += flow
        predicted_frame = cv2.remap(
            frame,
            flow_map[:, :, 0].astype(np.float32),
            flow_map[:, :, 1].astype(np.float32),
            cv2.INTER_LINEAR
        )

    prev_gray[0] = gray

    # ── YOLO DETECTION ────────────────────────────────────────
    results = model(frame, conf=0.4, verbose=False)
    boxes = results[0].boxes
    brake_active[0] = False
    frame_area = frame.shape[0] * frame.shape[1]
    detection_frame = frame.copy()

    for box in boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        cls = int(box.cls)
        conf = float(box.conf)
        name = model.names[cls]
        proximity = ((x2 - x1) * (y2 - y1)) / frame_area

        if name not in ['car', 'truck', 'bus', 'person',
                        'bicycle', 'motorcycle']:
            continue

        color = (0, 255, 0)
        if proximity > 0.05:
            color = (0, 0, 255)
            brake_active[0] = True
            try:
                vehicle.set_autopilot(False, 8000)
                vehicle.apply_control(
                    carla.VehicleControl(brake=1.0, throttle=0.0)
                )
            except:
                pass

        cv2.rectangle(detection_frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(detection_frame,
                   f'{name} {conf:.2f} {proximity:.2f}',
                   (x1, y1 - 5),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

    # ── HUD ───────────────────────────────────────────────────
    try:
        v_vel = vehicle.get_velocity()
        speed = 3.6 * (v_vel.x**2 + v_vel.y**2 + v_vel.z**2)**0.5
    except:
        break

    cv2.putText(detection_frame, f'Speed: {speed:.1f} km/h',
               (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(detection_frame, f'Objects: {len(boxes)}',
               (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    if brake_active[0]:
        cv2.rectangle(detection_frame, (0, 0), (640, 480), (0, 0, 255), 8)
        cv2.putText(detection_frame, '⚠ BRAKE OVERRIDE',
                   (120, 240), cv2.FONT_HERSHEY_SIMPLEX,
                   1.2, (0, 0, 255), 3)
    else:
        try:
            vehicle.set_autopilot(True, 8000)
            tm.ignore_lights_percentage(vehicle, 100)
        except:
            pass

    # ── LABELS ────────────────────────────────────────────────
    cv2.putText(detection_frame, 'LIVE DETECTION + YOLO',
               (10, 470), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
    cv2.putText(predicted_frame, 'OPTICAL FLOW PREDICTION',
               (10, 470), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)

    # ── DISPLAY ───────────────────────────────────────────────
    display = np.hstack([detection_frame, predicted_frame])
    cv2.imshow('GhostDriver — Detection | Prediction', display)

    if cv2.waitKey(1) == ord('q'):
        break

# ── CLEANUP ───────────────────────────────────────────────────
cv2.destroyAllWindows()
try:
    camera.stop()
    camera.destroy()
    vehicle.destroy()
except:
    pass
for v in traffic + bicycles:
    try: v.destroy()
    except: pass
for c in walker_controllers:
    try: c.stop(); c.destroy()
    except: pass
for w in walkers:
    try: w.destroy()
    except: pass
print("✅ Done")