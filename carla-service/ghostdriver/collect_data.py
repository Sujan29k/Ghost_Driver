import carla
import os
import time
import random
import cv2
import numpy as np

# Connect
client = carla.Client('localhost', 2000)
client.set_timeout(60.0)
world = client.get_world()
print("✅ Connected:", world.get_map().name)

bp_lib = world.get_blueprint_library()
spectator = world.get_spectator()
spawn_points = world.get_map().get_spawn_points()

# Spawn ego vehicle
vehicle_bp = bp_lib.filter('vehicle.tesla.model3')[0]
vehicle = world.spawn_actor(vehicle_bp, spawn_points[0])
vehicle.set_autopilot(True)
print("✅ Ego vehicle spawned")

# Spawn traffic vehicles
traffic_vehicles = []
for i in range(1, 30):
    try:
        v_bp = random.choice(bp_lib.filter('vehicle.*'))
        v = world.spawn_actor(v_bp, spawn_points[i])
        v.set_autopilot(True)
        traffic_vehicles.append(v)
    except:
        pass
print(f"✅ {len(traffic_vehicles)} traffic vehicles spawned")

# Spawn pedestrians
walker_bps = bp_lib.filter('walker.pedestrian.*')
walkers = []
walker_controllers = []
walker_controller_bp = bp_lib.find('controller.ai.walker')

for i in range(20):
    try:
        walker_bp = random.choice(walker_bps)
        walker_spawn = carla.Transform()
        walker_spawn.location = world.get_random_location_from_navigation()
        if walker_spawn.location:
            walker = world.spawn_actor(walker_bp, walker_spawn)
            walkers.append(walker)
            controller = world.spawn_actor(walker_controller_bp, carla.Transform(), walker)
            walker_controllers.append(controller)
    except:
        pass

world.wait_for_tick()

for controller in walker_controllers:
    try:
        controller.start()
        controller.go_to_location(world.get_random_location_from_navigation())
        controller.set_max_speed(1.4)
    except:
        pass
print(f"✅ {len(walkers)} pedestrians spawned")

# Camera setup
camera_bp = bp_lib.find('sensor.camera.rgb')
camera_bp.set_attribute('image_size_x', '1280')
camera_bp.set_attribute('image_size_y', '720')
camera_bp.set_attribute('fov', '90')
camera = world.spawn_actor(
    camera_bp,
    carla.Transform(carla.Location(x=2.0, z=1.5)),
    attach_to=vehicle
)
print("✅ Camera attached")
print("📷 Live camera window will open — press Q to skip to next condition")

# Chaotic weather conditions
weathers = {
    'clear_traffic': carla.WeatherParameters.ClearNoon,
    'heavy_rain':    carla.WeatherParameters.HardRainNoon,
    'fog_night':     carla.WeatherParameters.ClearNight,
    'storm':         carla.WeatherParameters(
                        cloudiness=100,
                        precipitation=100,
                        precipitation_deposits=100,
                        wind_intensity=100,
                        fog_density=50,
                        wetness=100
                     ),
    'dust_sunset':   carla.WeatherParameters(
                        cloudiness=60,
                        precipitation=0,
                        sun_altitude_angle=5,
                        fog_density=30,
                        wind_intensity=80
                     ),
    'night_rain':    carla.WeatherParameters(
                        cloudiness=100,
                        precipitation=80,
                        sun_altitude_angle=-90,
                        fog_density=20,
                        wetness=100
                     ),
}

for condition, weather in weathers.items():
    print(f"\n🌩 Condition: {condition}")
    world.set_weather(weather)
    os.makedirs(f'dataset/{condition}', exist_ok=True)

    frame_count = [0]
    latest_frame = [None]

    def save_frame(image):
        # Move spectator
        t = vehicle.get_transform()
        spectator.set_transform(carla.Transform(
            t.location + carla.Location(z=50),
            carla.Rotation(pitch=-90)
        ))

        # Convert to numpy for live display
        array = np.frombuffer(image.raw_data, dtype=np.uint8)
        array = array.reshape((image.height, image.width, 4))
        bgr = array[:, :, :3]
        latest_frame[0] = bgr

        # Save every 2nd frame
        if frame_count[0] % 2 == 0:
            image.save_to_disk(f'dataset/{condition}/{frame_count[0]:06d}.jpg')
            if frame_count[0] % 100 == 0:
                print(f"  Saved frame {frame_count[0]}")
        frame_count[0] += 1

    camera.listen(save_frame)

    # Show live camera feed for 60 seconds
    start = time.time()
    while time.time() - start < 60:
        if latest_frame[0] is not None:
            # Add condition text on frame
            display = latest_frame[0].copy()
            cv2.putText(display, f'Condition: {condition}', (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.putText(display, f'Frames: {frame_count[0]}', (10, 70),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.imshow('GhostDriver Camera Feed', display)

        key = cv2.waitKey(1)
        if key == ord('q'):
            break

    camera.stop()
    print(f"✅ {condition} done — {frame_count[0] // 2} frames saved")

cv2.destroyAllWindows()

# Cleanup
print("\nCleaning up...")
camera.destroy()
vehicle.destroy()
for v in traffic_vehicles:
    try: v.destroy()
    except: pass
for c in walker_controllers:
    try: c.stop(); c.destroy()
    except: pass
for w in walkers:
    try: w.destroy()
    except: pass

print("✅ All done! Check dataset/ folder")