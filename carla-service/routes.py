"""Bounded lane-following routes for Traffic Manager; no extra CARLA agents package."""
import math
import random


def distance(a, b):
    return math.sqrt((a.x-b.x)**2 + (a.y-b.y)**2 + (a.z-b.z)**2)


class RoutePlanner:
    def __init__(self, world, vehicle, seed=2026):
        self.map, self.vehicle, self.seed = world.get_map(), vehicle, seed
        self.points = []
        self.index = 0
        self.length = 0
        self.name = None
        self.options = [{'id': 'straight', 'label': 'Follow lane · prefer straight'},
                        {'id': 'left', 'label': 'Follow lane · prefer left at junctions'},
                        {'id': 'right', 'label': 'Follow lane · prefer right at junctions'}]

    def select(self, name, length=300):
        if name not in ('straight', 'left', 'right'):
            raise ValueError('Unknown route')
        waypoint = self.map.get_waypoint(self.vehicle.get_location())
        if waypoint is None:
            raise ValueError('Vehicle is not near a drivable lane')
        points, visited = [waypoint.transform.location], set()
        rng = random.Random(self.seed)
        for _ in range(int(length / 4)):
            candidates = list(waypoint.next(4.0))
            if not candidates:
                break
            rng.shuffle(candidates)
            yaw = waypoint.transform.rotation.yaw
            def turn(candidate):
                return (candidate.transform.rotation.yaw - yaw + 180) % 360 - 180
            # CARLA/Unreal axes: positive yaw is a right turn.
            candidates.sort(key=lambda w: abs(turn(w)) if name == 'straight' else turn(w) * (1 if name == 'left' else -1))
            waypoint = candidates[0]
            key = (waypoint.road_id, waypoint.section_id, waypoint.lane_id, round(waypoint.s / 2))
            if key in visited:
                break
            visited.add(key)
            points.append(waypoint.transform.location)
        if len(points) < 3:
            raise ValueError('No usable route ahead; reposition the vehicle or change map')
        self.points, self.index, self.name = points, 0, name
        self.length = sum(distance(a, b) for a, b in zip(points, points[1:]))
        return self.snapshot()

    def observe(self, location):
        if not self.points:
            return {'progress': 0, 'deviation': 0, 'finished': False}
        # Search a local forward window so looping/crossing roads do not jump route progress.
        candidates = range(max(0, self.index - 2), min(len(self.points), self.index + 15))
        nearest = min(candidates, key=lambda i: distance(location, self.points[i]))
        self.index = max(self.index, nearest)
        progress = sum(distance(a, b) for a, b in zip(self.points[:self.index], self.points[1:self.index + 1]))
        return {'progress': progress, 'deviation': distance(location, self.points[nearest]),
                'finished': distance(location, self.points[-1]) < 4 and self.index >= len(self.points)-3}

    def snapshot(self):
        return {'name': self.name, 'lengthMeters': self.length, 'options': self.options,
                'points': [{'x': p.x, 'y': p.y, 'z': p.z} for p in self.points]}
