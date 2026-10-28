"""Owned CARLA scenarios. Flood/landslide presets are explicitly approximations."""
import random
from routes import distance

SCENARIOS = ('normal', 'rain', 'landslide', 'flood', 'combined')


class ScenarioManager:
    def __init__(self, world, carla, vehicle):
        self.world, self.carla, self.vehicle = world, carla, vehicle
        self.actors = []
        self.original_weather = None
        self.hazard = None
        self.state = {'name': 'none', 'active': False, 'warnings': [], 'severity': 1}

    def reset(self):
        failed = []
        for actor in reversed(self.actors):
            try:
                if actor.destroy() is False:
                    failed.append(actor)
            except Exception:
                failed.append(actor)
        self.actors = failed
        if self.original_weather is not None:
            self.world.set_weather(self.original_weather)
            self.original_weather = None
        self.hazard = None
        self.state = {'name': 'none', 'active': False, 'warnings': [], 'severity': 1}
        if failed:
            raise RuntimeError('Some scenario actors could not be removed; retry reset')

    def start(self, name, severity=1, seed=2026, blockage='partial', route=None, weather_settings=None):
        if name not in SCENARIOS or type(severity) is not int or severity not in (1, 2, 3):
            raise ValueError('Invalid scenario or severity')
        if blockage not in ('partial', 'full'):
            raise ValueError('Blockage must be partial or full')
        self.reset()
        self.original_weather = self.world.get_weather()
        weather = self.world.get_weather()
        wet = name in ('rain', 'flood', 'combined')
        weather.cloudiness = 90 if wet else 10
        weather.precipitation = (35, 65, 95)[severity-1] if wet else 0
        weather.precipitation_deposits = 90 if name in ('flood', 'combined') else (60 if wet else 0)
        weather.wetness = 100 if wet else 0
        weather.fog_density = (10, 30, 60)[severity-1] if wet else 0
        weather.sun_altitude_angle = 15 if wet else 65
        values = weather_settings or {}
        if wet:
            for key, attribute in {'precipitation': 'precipitation', 'wetness': 'wetness',
                                   'puddles': 'precipitation_deposits', 'fogDensity': 'fog_density',
                                   'sunAltitude': 'sun_altitude_angle'}.items():
                if key in values:
                    setattr(weather, attribute, values[key])
        self.state = {'name': name, 'active': True, 'severity': severity, 'seed': seed,
                      'blockage': blockage, 'warnings': [], 'map': self.world.get_map().name,
                      'weather': {k: getattr(weather, k) for k in ('cloudiness', 'precipitation',
                          'precipitation_deposits', 'wetness', 'fog_density', 'sun_altitude_angle')},
                      'effects': [], 'actors': [], 'egoSpawn': self._xyz(self.vehicle.get_location()),
                      'expectedTakeover': ('No scripted trigger' if name == 'normal' else 'Full blockage may be impassable; stop rather than force through' if blockage == 'full' else 'Configured weather/hazard and sensor policy stop the car before operator response'),
                      'triggerConditions': ('none beyond simulator faults' if name == 'normal' else 'scripted hazard distance, configured weather threshold, collision/obstacle sensor, route stall/deviation'),
                      'requiredAssets': (['stock weather fields', 'static.trigger.friction'] if wet else ['stock map and vehicle blueprints']) + (['static.prop.rock/stone/debris (discovered at runtime)'] if name in ('landslide', 'combined') else []),
                      'fallbackBehavior': ('static collision props or labelled generic parked-vehicle obstacle' if name in ('landslide', 'combined') else 'Flood is visual weather, low-friction zone and scripted trigger only' if name == 'flood' else 'No custom assets required'),
                      'hazard': None, 'friction': None, 'route': route or {}}
        try:
            self.world.set_weather(weather)
            if name == 'normal':
                return self.snapshot()
            waypoint = self.world.get_map().get_waypoint(self.vehicle.get_location())
            if waypoint is None:
                raise ValueError('Place the ego on a road before starting a scenario')
            # Follow the selected route where possible, rather than a random distant map point.
            points = (route or {}).get('points', [])
            if len(points) > 9:
                locations = [self.carla.Location(**point) for point in points]
                closest = min(range(len(locations)), key=lambda i: distance(locations[i], self.vehicle.get_location()))
                target = locations[min(closest + 9, len(locations) - 1)]
                if distance(target, self.vehicle.get_location()) < 15:
                    raise ValueError('Route ends too soon for a hazard; choose a new route before this scenario')
                ahead = self.world.get_map().get_waypoint(target)
            else:
                choices = waypoint.next(36.0)
                ahead = choices[0] if choices else waypoint
            if ahead is None:
                raise ValueError('No road available for the hazard')
            self.hazard = ahead.transform.location
            self.state['hazard'] = self._xyz(self.hazard)
            if wet:
                self._friction(ahead, values.get('friction', (.8, .5, .3)[severity-1]))
                self.state['effects'].append('Visual weather plus a local low-friction zone')
            if name in ('landslide', 'combined'):
                self._obstruction(ahead, blockage, seed)
            if name in ('flood', 'combined'):
                self.state['effects'].append('FLOOD APPROXIMATION: puddles, low friction, scripted hazard zone')
                self.state['warnings'].append('FLOOD APPROXIMATION: configured puddles, friction and scripted zone; no water depth, buoyancy, flow forces or engine flooding')
            return self.snapshot()
        except Exception:
            self.reset()
            raise

    def _friction(self, waypoint, friction):
        blueprints = list(self.world.get_blueprint_library().filter('static.trigger.friction'))
        if not blueprints:
            raise ValueError('Map installation lacks static.trigger.friction; physical scenario unavailable')
        bp = blueprints[0]
        # CARLA friction extents are centimeters, not meters.
        for key, value in {'friction': friction, 'extent_x': 800, 'extent_y': 500, 'extent_z': 200}.items():
            bp.set_attribute(key, str(value))
        actor = self.world.spawn_actor(bp, waypoint.transform)
        self.actors.append(actor)
        self.state['friction'] = friction
        self.state['actors'].append({'blueprint': bp.id, 'id': actor.id})

    def _obstruction(self, waypoint, blockage, seed):
        library = self.world.get_blueprint_library()
        props = [bp for bp in library.filter('static.prop.*') if any(word in bp.id.lower() for word in ('rock', 'stone', 'debris'))]
        rng = random.Random(seed)
        fallback = not props
        if fallback:
            # A stationary vehicle provides real collision geometry in stock packages.
            props = list(library.filter('vehicle.*'))
            props = [bp for bp in props if bp.has_attribute('number_of_wheels') and bp.get_attribute('number_of_wheels').as_int() == 4]
            self.state['warnings'].append('GENERIC ROADBLOCK fallback: parked vehicles; no landslide assets available')
        if not props:
            raise ValueError('No collision obstacle blueprint available')
        right = waypoint.transform.get_right_vector()
        offsets = [waypoint.lane_width * .25] if blockage == 'partial' else [-waypoint.lane_width * .25, waypoint.lane_width * .25]
        spawned = 0
        for index, offset in enumerate(offsets):
            loc = waypoint.transform.location
            forward = waypoint.transform.get_forward_vector()
            location = self.carla.Location(x=loc.x + right.x * offset + forward.x * index * 5,
                y=loc.y + right.y * offset + forward.y * index * 5, z=loc.z + .4)
            blueprint = rng.choice(props)
            transform = self.carla.Transform(location, waypoint.transform.rotation)
            actor = self.world.try_spawn_actor(blueprint, transform)
            if actor is None:
                continue
            self.actors.append(actor)
            if fallback:
                actor.set_autopilot(False)
                actor.apply_control(self.carla.VehicleControl(brake=1.0, hand_brake=True))
            self.state['actors'].append({'id': actor.id, 'blueprint': blueprint.id, 'location': self._xyz(location)})
            spawned += 1
        if not spawned:
            raise ValueError('Obstacle spawn positions occupied; reset or reposition and retry')
        self.state['effects'].append('LANDSLIDE APPROXIMATION: static collision obstacles, not moving soil physics')
        self.state['warnings'].append('Verify obstacle collision and actual passability in CARLA; blockage is a requested layout')

    def hazard_distance(self, location):
        return distance(location, self.hazard) if self.hazard is not None else None

    def snapshot(self):
        return {**self.state, 'warnings': list(self.state['warnings'])}

    @staticmethod
    def _xyz(location):
        return {'x': location.x, 'y': location.y, 'z': location.z}
