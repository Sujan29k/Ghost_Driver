/**
 * Control Socket Handler
 * Receives keyboard/gamepad control commands from the operator dashboard
 * and forwards them to the CARLA service.
 */

const carlaService = require('../services/carla.service');

const KEY_MAP = {
  w: { throttle: 1, brake: 0, steer: 0 },
  s: { throttle: 0, brake: 1, steer: 0 },
  a: { throttle: 0, brake: 0, steer: -0.5 },
  d: { throttle: 0, brake: 0, steer: 0.5 },
  ' ': { throttle: 0, brake: 1, steer: 0, emergency: true },
};

function registerHandlers(socket, io) {
  // Key-based control
  socket.on('control:key', ({ key, type }) => {
    if (type === 'keydown') {
      const cmd = KEY_MAP[key?.toLowerCase()];
      if (!cmd) return;

      if (cmd.emergency) {
        carlaService.emergencyStop();
        io.emit('vehicle:emergency-stop', { triggeredBy: socket.id, ts: Date.now() });
        console.log(`[Control] EMERGENCY STOP by ${socket.id}`);
      } else {
        carlaService.applyControl(cmd);
      }
    } else if (type === 'keyup') {
      // Release — coast
      carlaService.applyControl({ throttle: 0, brake: 0, steer: 0 });
    }
  });

  // Direct control values (gamepad / slider)
  socket.on('control:direct', ({ throttle, brake, steer }) => {
    carlaService.applyControl({ throttle, brake, steer });
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
