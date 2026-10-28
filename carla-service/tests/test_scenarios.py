import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scenarios import ScenarioManager

class ScenarioTest(unittest.TestCase):
    def test_failed_destroy_retains_owned_actor_for_retry(self):
        actor = SimpleNamespace(destroy=lambda: False)
        manager = ScenarioManager(SimpleNamespace(), SimpleNamespace(), SimpleNamespace())
        manager.actors = [actor]
        with self.assertRaisesRegex(RuntimeError, 'retry reset'):
            manager.reset()
        self.assertEqual(manager.actors, [actor])
        actor.destroy = lambda: True
        manager.reset()
        self.assertEqual(manager.actors, [])

    def test_weather_physics_hazards_cleanup_and_weather_restore(self):
        class Actor:
            id = 5
            def __init__(self): self.destroyed = False
            def destroy(self): self.destroyed = True
        class BP:
            id='static.trigger.friction'
            def set_attribute(self,*_): pass
            def has_attribute(self,*_): return False
        class Waypoint:
            lane_width=3.5
            transform=SimpleNamespace(location=SimpleNamespace(x=1,y=2,z=0), rotation=None,
                get_right_vector=lambda:SimpleNamespace(x=0,y=1,z=0), get_forward_vector=lambda:SimpleNamespace(x=1,y=0,z=0))
            def next(self,_): return [self]
        actor=Actor(); original=SimpleNamespace(cloudiness=15, precipitation=0, precipitation_deposits=0, wetness=0, fog_density=0, sun_altitude_angle=70)
        library=SimpleNamespace(filter=lambda pattern: [BP()] if pattern=='static.trigger.friction' else [])
        world=SimpleNamespace(get_weather=lambda:SimpleNamespace(**vars(original)), set_weather=lambda w:setattr(world,'weather',w),
            get_map=lambda:SimpleNamespace(name='Town01',get_waypoint=lambda *_:Waypoint()),
            get_blueprint_library=lambda:library,spawn_actor=lambda *_:actor,try_spawn_actor=lambda *_:None)
        carla=SimpleNamespace(Location=lambda **kw:SimpleNamespace(**kw),VehicleControl=lambda **kw:kw,Transform=lambda *a:a)
        vehicle=SimpleNamespace(get_location=lambda:SimpleNamespace(x=0,y=0,z=0))
        manager=ScenarioManager(world,carla,vehicle)
        state=manager.start('rain',2,seed=3)
        self.assertEqual(state['friction'],.5)
        self.assertIn('low-friction',state['effects'][0])
        manager.reset()
        self.assertTrue(actor.destroyed)
        self.assertEqual(world.weather.cloudiness,15)
        flood=manager.start('flood',1,seed=3)
        self.assertTrue(any('FLOOD APPROXIMATION' in w for w in flood['warnings']))
        manager.reset()


class ObstructionCleanupTest(unittest.TestCase):
    def test_generic_fallback_reset_and_partial_failure_preserve_external_actors(self):
        from copy import deepcopy
        original = SimpleNamespace(cloudiness=15, precipitation=0, precipitation_deposits=0,
            wetness=0, fog_density=0, sun_altitude_angle=70)
        spawned, removed = [], []
        external = SimpleNamespace(id=999, alive=True)
        class Blueprint:
            def __init__(self, name): self.id = name
            def set_attribute(self, *_): pass
            def has_attribute(self, name): return name == 'number_of_wheels'
            def get_attribute(self, _): return SimpleNamespace(as_int=lambda: 4)
        class Waypoint:
            lane_width = 3.5
            transform = SimpleNamespace(location=SimpleNamespace(x=36, y=0, z=0), rotation=None,
                get_right_vector=lambda: SimpleNamespace(x=0, y=1, z=0),
                get_forward_vector=lambda: SimpleNamespace(x=1, y=0, z=0))
            def next(self, _): return [self]
        def spawn(*_):
            actor = SimpleNamespace(id=len(spawned)+1, set_autopilot=lambda *_: None, apply_control=lambda *_: None)
            actor.destroy = lambda: removed.append(actor.id)
            spawned.append(actor)
            return actor
        library = SimpleNamespace(filter=lambda pattern: [] if pattern == 'static.prop.*' else [Blueprint(pattern)])
        world = SimpleNamespace(get_weather=lambda: deepcopy(original), set_weather=lambda w: setattr(world, 'weather', w),
            get_map=lambda: SimpleNamespace(name='Fixture', get_waypoint=lambda *_: Waypoint()),
            get_blueprint_library=lambda: library, spawn_actor=spawn, try_spawn_actor=spawn)
        carla = SimpleNamespace(Location=lambda **kw: SimpleNamespace(**kw), Transform=lambda *args: args, VehicleControl=lambda **kw: kw)
        manager = ScenarioManager(world, carla, SimpleNamespace(get_location=lambda: SimpleNamespace(x=0, y=0, z=0)))
        state = manager.start('landslide', blockage='full')
        self.assertEqual(len(manager.actors), 2)
        self.assertTrue(any('GENERIC ROADBLOCK' in warning for warning in state['warnings']))
        manager.start('landslide', blockage='partial')
        self.assertEqual(removed, [2, 1])
        self.assertEqual(len(manager.actors), 1)
        manager.reset()
        self.assertEqual(world.weather.cloudiness, original.cloudiness)
        self.assertTrue(external.alive)
        # A combined scenario creates friction first; failed obstruction spawning
        # must remove that owned trigger and restore the original weather too.
        world.try_spawn_actor = lambda *_: None
        with self.assertRaisesRegex(ValueError, 'spawn positions occupied'):
            manager.start('combined', severity=3)
        self.assertEqual(manager.actors, [])
        self.assertEqual(world.weather.precipitation, 0)
        self.assertEqual(len(removed), len(spawned))

if __name__ == '__main__':
    unittest.main()
