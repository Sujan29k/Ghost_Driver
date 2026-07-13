/**
 * CARLA Service
 * Stub for Phase 1. Will connect to the Python CARLA controller in Phase 2.
 *
 * Simulates realistic telemetry data so the dashboard is fully functional
 * without a running CARLA instance.
 */

let _connected = false;
let _simInterval = null;
let _onTelemetry = null; // callback (data) => void

// Simulated vehicle state
let _state = {
  speed: 0,
  throttle: 0,
  brake: 0,
  steer: 0,
  gear: 'P',
  heading: 0,
  lat: 48.8566,
  lon: 2.3522,
  altitude: 10,
};

function connect() {
  if (_connected) return { success: true, message: 'Already connected' };
  _connected = true;
  console.log('[CARLA] Simulated connection established');
  _startTelemetrySim();
  return { success: true, message: 'Connected to CARLA (simulated)' };
}

function disconnect() {
  _connected = false;
  _stopTelemetrySim();
  console.log('[CARLA] Disconnected');
  return { success: true, message: 'Disconnected from CARLA' };
}

function isConnected() {
  return _connected;
}

function applyControl({ throttle = 0, brake = 0, steer = 0 }) {
  if (!_connected) return { success: false, message: 'Not connected' };
  _state.throttle = throttle;
  _state.brake = brake;
  _state.steer = steer;

  // Simulate speed response
  _state.speed += throttle * 2 - brake * 3;
  _state.speed = Math.max(0, Math.min(120, _state.speed));

  return { success: true };
}

function emergencyStop() {
  _state.throttle = 0;
  _state.brake = 1;
  _state.speed = 0;
  console.log('[CARLA] EMERGENCY STOP triggered');
  return { success: true, message: 'Emergency stop applied' };
}

function onTelemetry(cb) {
  _onTelemetry = cb;
}

function _startTelemetrySim() {
  _simInterval = setInterval(() => {
    // Drift speed slightly
    _state.speed = Math.max(0, _state.speed + (Math.random() - 0.5) * 0.5);
    _state.heading = (_state.heading + 0.5) % 360;

    const data = {
      timestamp: Date.now(),
      speed: parseFloat(_state.speed.toFixed(1)),
      throttle: _state.throttle,
      brake: _state.brake,
      steer: _state.steer,
      gear: _state.gear,
      heading: parseFloat(_state.heading.toFixed(1)),
      location: { lat: _state.lat, lon: _state.lon, altitude: _state.altitude },
      carlaConnected: true,
    };

    if (_onTelemetry) _onTelemetry(data);
  }, 200);
}

function _stopTelemetrySim() {
  if (_simInterval) {
    clearInterval(_simInterval);
    _simInterval = null;
  }
}

module.exports = { connect, disconnect, isConnected, applyControl, emergencyStop, onTelemetry };
