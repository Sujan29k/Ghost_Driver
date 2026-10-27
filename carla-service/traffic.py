"""Own and clean up only the background actors created by this bridge."""
import logging
import random

log = logging.getLogger('ghostdriver')


class TrafficScene:
    def __init__(self, world, carla, seed=42):
        self.world, self.carla = world, carla
        self.random = random.Random(seed)
        self.vehicles, self.walkers, self.controllers = [], [], []
        self.counts = {'vehicles': 0, 'bicycles': 0, 'pedestrians': 0}
        self.manager = None

    def spawn(self, client, ego, vehicles=30, bicycles=5, pedestrians=20, port=8000):
        if not any((vehicles, bicycles, pedestrians)):
            return
        self.manager = client.get_trafficmanager(port)
        self.manager.set_synchronous_mode(False)
        library = self.world.get_blueprint_library()
        blueprints = list(library.filter('vehicle.*'))
        cars = [bp for bp in blueprints if bp.has_attribute('number_of_wheels')
                and bp.get_attribute('number_of_wheels').as_int() == 4]
        bikes = [bp for bp in blueprints if bp.id in
                 ('vehicle.bh.crossbike', 'vehicle.diamondback.century', 'vehicle.gazelle.omafiets')]
        origin = ego.get_location()
        points = list(self.world.get_map().get_spawn_points())
        # Prefer nearby traffic instead of populating the far end of a large map.
        points.sort(key=lambda p: p.location.distance(origin))
        # Also try driving-lane waypoints ahead of the ego camera. Occupied
        # positions are skipped by try_spawn_actor, never forced into collisions.
        waypoint = self.world.get_map().get_waypoint(origin)
        ahead = []
        if waypoint:
            for distance in (25, 45, 65):
                for wp in waypoint.next(distance):
                    transform = wp.transform
                    transform.location.z += 0.5
                    ahead.append(transform)
        points = ahead + points
        for label, requested, choices in [('vehicles', vehicles, cars), ('bicycles', bicycles, bikes)]:
            if not choices:
                if requested:
                    log.warning('No blueprints for %s', label)
                continue
            for transform in points:
                if self.counts[label] >= requested:
                    break
                if transform.location.distance(origin) < 12:
                    continue
                bp = self.random.choice(choices)
                if bp.has_attribute('role_name'):
                    bp.set_attribute('role_name', 'ghostdriver_traffic')
                actor = self.world.try_spawn_actor(bp, transform)
                if actor is None:
                    continue
                self.vehicles.append(actor)  # Own it before any later RPC can fail.
                actor.set_autopilot(True, port)
                self.counts[label] += 1
        walker_bps = list(library.filter('walker.pedestrian.*'))
        if pedestrians and walker_bps:
            controller_bp = library.find('controller.ai.walker')
            # Bound attempts when navigation positions are unavailable/occupied.
            for _ in range(pedestrians * 5):
                if len(self.controllers) >= pedestrians:
                    break
                location = self.world.get_random_location_from_navigation()
                if location is None:
                    continue
                bp = self.random.choice(walker_bps)
                if bp.has_attribute('is_invincible'):
                    bp.set_attribute('is_invincible', 'true')
                walker = self.world.try_spawn_actor(bp, self.carla.Transform(location))
                if walker is None:
                    continue
                self.walkers.append(walker)
                controller = self.world.try_spawn_actor(controller_bp, self.carla.Transform(), attach_to=walker)
                if controller is None:
                    walker.destroy()
                    self.walkers.remove(walker)
                    continue
                self.controllers.append(controller)
            if self.controllers:
                self.world.wait_for_tick(10.0)
            for controller in self.controllers:
                controller.start()
                target = self.world.get_random_location_from_navigation()
                if target is not None:
                    controller.go_to_location(target)
                controller.set_max_speed(1.4)
            self.counts['pedestrians'] = len(self.controllers)
        log.info('Spawned background traffic: %s', self.counts)
        for label, requested in [('vehicles', vehicles), ('bicycles', bicycles), ('pedestrians', pedestrians)]:
            if self.counts[label] < requested:
                log.warning('%s: spawned %s of %s; map/occupied positions limit availability',
                            label, self.counts[label], requested)

    def close(self):
        for controller in self.controllers:
            try:
                controller.stop()
            except Exception:
                log.warning('Could not stop walker controller %s', controller.id)
        for actor in self.controllers + self.walkers + self.vehicles:
            try:
                actor.destroy()
            except Exception:
                log.warning('Could not destroy owned actor %s', actor.id)
        self.controllers.clear()
        self.walkers.clear()
        self.vehicles.clear()
