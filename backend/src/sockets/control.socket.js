/**
 * Control Socket Handler
 * Receives keyboard/gamepad control commands from the operator dashboard
 * and forwards them to the CARLA service.
 */

const carlaService = require('../services/carla.service');
const latencyService = require('../services/latency.service');

const KEY_MAP = {
  w: { throttle: 1, brake: 0, steer: 0 },
  s: { throttle: 0, brake: 1, steer: 0 },
  a: { throttle: 0, brake: 0, steer: -0.5 },
  d: { throttle: 0, brake: 0, steer: 0.5 },
  ' ': { throttle: 0, brake: 1, steer: 0, emergency: true },
};

function registerHandlers(socket, io) {
  socket.emit('latency:configure', { latencyMs: latencyService.getInjectedLatency() });

  const emitControlToBridge = (cmd) => {
    io.emit('control:apply', {
      ...cmd,
      source: 'dashboard',
      timestamp: Date.now(),
    });
  };

  socket.on('latency:configure', ({ latencyMs } = {}) => {
    const value = Number(latencyMs);
    if (!latencyService.setInjectedLatency(value)) {
      socket.emit('latency:configured', {
        success: false,
        latencyMs: latencyService.getInjectedLatency(),
      });
      return;
    }

    io.emit('latency:configure', { latencyMs: value });
    io.emit('latency:configured', { success: true, latencyMs: value });
    console.log(`[Latency] Injected delay set to ${value}ms by ${socket.id}`);
  });

  // Key-based control
  socket.on('control:key', ({ key, type }) => {
    if (type === 'keydown') {
      const cmd = KEY_MAP[key?.toLowerCase()];
      if (!cmd) return;

      if (cmd.emergency) {
        carlaService.emergencyStop();
        emitControlToBridge({ throttle: 0, brake: 1, steer: 0, emergency: true });
        io.emit('vehicle:emergency-stop', { triggeredBy: socket.id, ts: Date.now() });
        console.log(`[Control] EMERGENCY STOP by ${socket.id}`);
      } else {
        carlaService.applyControl(cmd);
        emitControlToBridge(cmd);
      }
    } else if (type === 'keyup') {
      // Release — coast
      const resetCmd = { throttle: 0, brake: 0, steer: 0 };
      carlaService.applyControl(resetCmd);
      emitControlToBridge(resetCmd);
    }
  });

  // Direct control values (gamepad / slider)
  socket.on('control:direct', ({ throttle, brake, steer }) => {
    const cmd = { throttle, brake, steer };
    carlaService.applyControl(cmd);
    emitControlToBridge(cmd);
  });

  // Connect vehicle
  socket.on('vehicle:connect', () => {
    const result = carlaService.connect();
    socket.emit('vehicle:connect:ack', result);
    io.emit('vehicle:status', { connected: carlaService.isConnected() });
    console.log(`[Control] Vehicle connect requested by ${socket.id}`);
  });

  // Disconnect vehicle
  socket.on('vehicle:disconnect', () => {
    const result = carlaService.disconnect();
    socket.emit('vehicle:disconnect:ack', result);
    io.emit('vehicle:status', { connected: false });
    console.log(`[Control] Vehicle disconnect requested by ${socket.id}`);
  });
}

module.exports = { registerHandlers };
