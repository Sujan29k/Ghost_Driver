import sys
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from traffic import TrafficScene


class Location:
    def __init__(self, x):
        self.x, self.z = x, 0

    def distance(self, other):
        return abs(self.x - other.x)


class Actor:
    def __init__(self, fails=False):
        self.id, self.destroyed, self.fails = 1, False, fails

    def set_autopilot(self, enabled, port):
        if self.fails:
            raise RuntimeError('RPC failed')
        self.autopilot = (enabled, port)

    def destroy(self):
        self.destroyed = True


class TrafficTest(unittest.TestCase):
    def scene(self, fails=False):
        actors = []
        bp = NS(id='vehicle.test', has_attribute=lambda name: name == 'number_of_wheels',
                get_attribute=lambda _: NS(as_int=lambda: 4))
        points = [NS(location=Location(x)) for x in (0, 20, 40)]
        def spawn(_, transform):
            if transform.location.x == 20:
                return None  # Occupied spawn point must be skipped.
            actor = Actor(fails)
            actors.append(actor)
            return actor
        world = NS(get_blueprint_library=lambda: NS(filter=lambda pattern: [bp] if pattern == 'vehicle.*' else []),
                   get_map=lambda: NS(get_spawn_points=lambda: points, get_waypoint=lambda _: None),
                   try_spawn_actor=spawn)
        client = NS(get_trafficmanager=lambda _: NS(set_synchronous_mode=lambda _: None))
        ego = NS(get_location=lambda: Location(0))
        return TrafficScene(world, None), client, ego, actors

    def test_small_map_and_occupied_spawns_report_actual_counts_and_cleanup(self):
        scene, client, ego, actors = self.scene()
        scene.spawn(client, ego, vehicles=30, bicycles=0, pedestrians=0)
        self.assertEqual(scene.counts['vehicles'], 1)
        self.assertEqual(actors[0].autopilot, (True, 8000))
        scene.close()
        self.assertTrue(actors[0].destroyed)
        scene.close()  # Cleanup is idempotent.

    def test_partial_startup_failure_still_owns_actor_for_cleanup(self):
        scene, client, ego, actors = self.scene(fails=True)
        with self.assertRaises(RuntimeError):
            scene.spawn(client, ego, vehicles=1, bicycles=0, pedestrians=0)
        scene.close()
        self.assertTrue(actors[0].destroyed)

    def test_disabled_scene_does_not_contact_traffic_manager(self):
        scene = TrafficScene(None, None)
        scene.spawn(None, None, vehicles=0, bicycles=0, pedestrians=0)
        self.assertEqual(scene.counts['vehicles'], 0)


if __name__ == '__main__':
    unittest.main()
