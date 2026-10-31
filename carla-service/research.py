"""Sender-owned driving authority and research operations for CARLA 0.9.15+."""
import math
import logging
import threading
import time
from recording import TrialRecorder
from routes import RoutePlanner
from scenarios import ScenarioManager
from takeover import TakeoverPolicy

log = logging.getLogger('ghostdriver')


class ResearchController:
    def __init__(self, world, client, carla, vehicle, controls, pipeline, record_dir,
                 tm_port=8000, seed=2026, direction_limit=1.0, metadata=None):
        self.world, self.client, self.carla, self.vehicle = world, client, carla, vehicle
        self.controls, self.pipeline = controls, pipeline
        self.tm_port, self.seed, self.direction_limit = tm_port, seed, direction_limit
        self.routes = RoutePlanner(world, vehicle, seed)
        self.scenarios = ScenarioManager(world, carla, vehicle)
        self.policy = TakeoverPolicy()
        self.recorder = TrialRecorder(record_dir)
        self.metadata = metadata or {}
        self.autopilot = False
        self.actuation_lock = threading.RLock()
        self.state_lock = threading.RLock()
        self.takeover = None
        self.route_observation = {'progress': 0, 'deviation': 0, 'finished': False}
        self.sensors = []
        self.collision = False
        self.obstacle_at = 0
        self.previous_mode = 'STOPPED'
        self.acknowledged_mode = 'STOPPED'
        self.tm = None

    def attach_sensors(self):
        library = self.world.get_blueprint_library()
        def add(name, callback, attributes=None):
            bp = library.find(name)
            for key, value in (attributes or {}).items():
                bp.set_attribute(key, str(value))
            sensor = self.world.spawn_actor(bp, self.carla.Transform(), attach_to=self.vehicle)
            self.sensors.append(sensor)
            sensor.listen(callback)
        def collision(event):
            with self.state_lock:
                self.collision = True
            self.recorder.record('sensor:collision', {'simulationFrame': event.frame,
                'otherActor': event.other_actor.id, 'type': event.other_actor.type_id})
        def obstacle(event):
            with self.state_lock:
                self.obstacle_at = time.monotonic()
            self.recorder.record('sensor:obstacle', {'simulationFrame': event.frame, 'distance': event.distance})
        def lane(event):
            self.recorder.record('sensor:lane', {'simulationFrame': event.frame,
                'markings': [str(mark.type) for mark in event.crossed_lane_markings]})
        add('sensor.other.collision', collision)
        add('sensor.other.lane_invasion', lane)
        add('sensor.other.obstacle', obstacle, {'distance': 12, 'hit_radius': .5,
            'only_dynamics': 'false', 'sensor_tick': .2})

    def speed(self):
        v = self.vehicle.get_velocity()
        return 3.6 * math.sqrt(v.x*v.x + v.y*v.y + v.z*v.z)

    def _disable_autopilot(self):
        if self.autopilot:
            self.vehicle.set_autopilot(False, self.tm_port)
            self.autopilot = False

    def _stopped(self):
        if self.speed() > self.direction_limit:
            raise ValueError(f'Stop below {self.direction_limit:g} km/h before changing this setting')

    def command(self, request):
        action, data = request['action'], request.get('data', {})
        generation = self.controls.begin_operation(request['commandId'], request.get('expectedGeneration'))
        self.recorder.record('operation:received', {'action': action, 'data': data})
        # Only scenario activation and recording can preserve autonomous authority.
        # Resets/configuration/gear changes always arrive behind a sequenced stop.
        preserve = (action == 'trial' or (action == 'scenario' and data.get('operation') == 'start'
                    and data.get('name') != 'none'))
        if not preserve:
            with self.actuation_lock:
                self._disable_autopilot()
                self.vehicle.apply_control(self.carla.VehicleControl(brake=1.0, reverse=self.controls.reverse))
        if action == 'mode':
            mode = data.get('mode')
            if mode not in ('MANUAL', 'AUTONOMOUS', 'STOPPED'):
                raise ValueError('Invalid driving mode')
            if mode == 'AUTONOMOUS':
                if self.takeover and self.acknowledged_mode == 'AUTONOMOUS':
                    raise ValueError('Take manual control to acknowledge the pending takeover first')
                self._stopped()
                if self.controls.reverse:
                    raise ValueError('Select Forward before starting autonomy')
                location = self.vehicle.get_location()
                if self.scenarios.hazard_distance(location) is not None and self.scenarios.hazard_distance(location) <= self.policy.settings['hazardDistance']:
                    raise ValueError('Move clear of the scripted hazard before returning to autonomy')
                if self.scenarios.state.get('weather', {}).get('precipitation', 0) >= self.policy.settings['weatherThreshold']:
                    raise ValueError('Configured weather trigger is still active; change/reset the scenario before autonomy')
                if any(not sensor.is_alive for sensor in self.sensors):
                    raise ValueError('Required safety sensor unavailable')
                if time.monotonic() - self.obstacle_at < .7:
                    raise ValueError('Clear the active obstacle before returning to autonomy')
                self.routes.select(self.routes.name or 'straight')
                if self.tm is None:
                    self.tm = self.client.get_trafficmanager(self.tm_port)
                if not hasattr(self.tm, 'set_path'):
                    raise ValueError('Installed CARLA Traffic Manager does not support set_path')
                self.policy.reset()
            with self.actuation_lock:
                # A disconnect/emergency during route work invalidates this operation.
                self.controls.transition(mode, generation)
                if mode == 'AUTONOMOUS':
                    try:
                        # The bridge owns an asynchronous world, including when
                        # background traffic is disabled. Register before routing.
                        self.tm.set_synchronous_mode(False)
                        self.vehicle.apply_control(self.carla.VehicleControl(
                            throttle=0.0, brake=0.0, hand_brake=False, reverse=False))
                        self.vehicle.set_autopilot(True, self.tm_port)
                        self.autopilot = True
                        self.tm.set_path(self.vehicle, self.routes.points)
                        self.tm.auto_lane_change(self.vehicle, False)
                        self.tm.vehicle_percentage_speed_difference(self.vehicle, 60)
                        self.tm.distance_to_leading_vehicle(self.vehicle, 5.0)
                        if self.controls.snapshot()['generation'] != generation:
                            raise ValueError('Autonomy cancelled by a newer safety stop')
                    except Exception:
                        self.controls.stop('Autonomous startup failed')
                        self._disable_autopilot()
                        self.vehicle.apply_control(self.carla.VehicleControl(brake=1.0))
                        raise
                with self.state_lock:
                    if mode == 'MANUAL' and request.get('previousMode') == 'AUTONOMOUS' and not self.takeover:
                        self.takeover = {'source': 'operator', 'reason': 'Operator requested manual control',
                                         'triggerNs': time.monotonic_ns()}
                        self.recorder.record('takeover:trigger', self.takeover)
                    if self.takeover and mode == 'MANUAL':
                        self.recorder.record('takeover:acknowledged', {'triggerNs': self.takeover['triggerNs']})
                    if mode == 'AUTONOMOUS':
                        self.takeover = None
                    if mode in ('MANUAL', 'AUTONOMOUS'):
                        self.collision = False
            self.acknowledged_mode = mode
            log.info('Driving mode acknowledged: %s', mode)
            self.recorder.record('mode:acknowledged', {'mode': mode, 'route': self.routes.snapshot()})
        elif action == 'direction':
            self._stopped()
            if data.get('direction') not in ('forward', 'reverse'):
                raise ValueError('Invalid direction')
            with self.controls.lock:
                if generation != self.controls.generation:
                    raise ValueError('Direction change cancelled by safety stop')
                self.controls.reverse = data['direction'] == 'reverse'
            self.recorder.record('direction', {'direction': data['direction']})
        elif action == 'video':
            if self.pipeline is None:
                raise ValueError('Start the sender with --ai yolo for comparison views')
            self.pipeline.configure(data.get('delayMs'), data.get('method'), data.get('view'), data.get('reference', False))
            self.recorder.record('video:configuration', self.pipeline.configuration())
        elif action == 'route':
            self._stopped()
            self.routes.select(data.get('route'))
            self.recorder.record('route', self.routes.snapshot())
        elif action == 'scenario':
            if not preserve:
                self._stopped()
            self.policy.reset()
            with self.state_lock:
                self.collision, self.takeover = False, None
            if data.get('name') == 'none':
                self.scenarios.reset()
            else:
                if not self.routes.points:
                    self.routes.select('straight')
                self.scenarios.start(data.get('name'), data.get('severity', 1), data.get('seed', self.seed),
                                     data.get('blockage', 'partial'), self.routes.snapshot(), data.get('weather'))
            self.recorder.record('scenario', self.scenarios.snapshot())
        elif action == 'buffer':
            if data.get('operation') != 'clear' or self.pipeline is None:
                raise ValueError('Video buffer is unavailable')
            self.pipeline.history.clear()
            self.recorder.record('video:buffer-cleared', {})
        elif action == 'policy':
            self.policy.configure(data)
            self.policy.reset()
            self.recorder.record('policy', self.policy.settings)
        elif action == 'trial':
            if data.get('operation') == 'start':
                self.recorder.start({**self.metadata, 'map': self.world.get_map().name,
                    'scenario': self.scenarios.snapshot(), 'route': self.routes.snapshot(),
                    'video': self.pipeline.configuration() if self.pipeline else None,
                    'policy': self.policy.settings, 'seed': self.scenarios.state.get('seed', self.seed)},
                    label=data.get('label', ''), save_frames=data.get('saveFrames', False), order=data.get('order', 1))
            elif data.get('operation') == 'stop':
                self.recorder.record('trial:outcome', {'outcome': data.get('outcome', 'unspecified')})
                self.recorder.stop()
            else:
                raise ValueError('Invalid trial operation')
        else:
            raise ValueError('Unknown research operation')
        if generation != self.controls.snapshot()['generation']:
            raise ValueError('Operation completed while a safety stop occurred; controls remain stopped')
        return self.snapshot()

    def tick(self):
        with self.actuation_lock:
            state = self.controls.snapshot()
            if self.routes.points:
                with self.state_lock:
                    self.route_observation = self.routes.observe(self.vehicle.get_location())
            if state['mode'] != 'AUTONOMOUS' or state['stopped']:
                self._disable_autopilot()
                throttle, brake, steer = self.controls.current()
                self.vehicle.apply_control(self.carla.VehicleControl(throttle=throttle, brake=brake,
                    steer=steer, reverse=self.controls.reverse))
            else:
                location = self.vehicle.get_location()
                observation = self.route_observation
                with self.state_lock:
                    self.route_observation = observation
                    collision = self.collision
                    blocked = time.monotonic() - self.obstacle_at < .7
                at_red = (self.vehicle.is_at_traffic_light() and
                          str(self.vehicle.get_traffic_light_state()).split('.')[-1] in ('Red', 'Yellow'))
                weather = self.scenarios.state.get('weather', {}).get('precipitation', 0)
                trigger = self.policy.evaluate(progress=observation['progress'], speed=self.speed(),
                    at_red_light=at_red, deviation=observation['deviation'],
                    hazard_distance=self.scenarios.hazard_distance(location), weather=weather,
                    collision=collision, sensor_fault=any(not s.is_alive for s in self.sensors), blocked=blocked)
                if observation['finished']:
                    self.controls.stop('Route complete')
                elif trigger:
                    with self.state_lock:
                        self.takeover = {**trigger, 'triggerNs': time.monotonic_ns()}
                    self.controls.stop(trigger['reason'], 'TAKEOVER_REQUESTED')
                    self.recorder.record('takeover:trigger', self.takeover)
                if self.controls.is_latched():
                    self._disable_autopilot()
                    self.vehicle.apply_control(self.carla.VehicleControl(brake=1.0))
        current_mode = self.controls.snapshot()['mode']
        if current_mode != self.previous_mode:
            log.info('Driving mode: %s -> %s (%s)', self.previous_mode, current_mode, self.controls.reason)
            self.recorder.record('mode:changed', {'previous': self.previous_mode, 'mode': current_mode,
                                               'reason': self.controls.reason})
            self.previous_mode = current_mode

    def snapshot(self):
        with self.state_lock:
            return {**self.controls.snapshot(), 'version': 1, 'directionLimitKmh': self.direction_limit,
                'takeover': dict(self.takeover) if self.takeover else None,
                'route': {'name': self.routes.name, 'lengthMeters': self.routes.length,
                          **self.route_observation, 'options': self.routes.options},
                'scenario': self.scenarios.snapshot(), 'policy': dict(self.policy.settings),
                'video': self.pipeline.configuration() if self.pipeline else None,
                'trial': self.recorder.state()}

    def close(self):
        self.controls.stop('Sender shutdown')
        with self.actuation_lock:
            self._disable_autopilot()
            self.vehicle.apply_control(self.carla.VehicleControl(brake=1.0))
        for sensor in self.sensors:
            try:
                sensor.stop()
                sensor.destroy()
            except Exception:
                pass
        self.sensors.clear()
        try:
            self.scenarios.reset()
        finally:
            self.recorder.stop()
