/**
 * Control Controller
 * Handles REST-based vehicle control commands.
 * Primary path uses Socket.IO for low latency; REST is a fallback.
 */

const carlaService = require('../services/carla.service');

/**
 * POST /api/control/command
 * Body: { throttle, brake, steer }
 */
function sendCommand(req, res) {
  const { throttle = 0, brake = 0, steer = 0 } = req.body;

  if (typeof throttle !== 'number' || typeof brake !== 'number' || typeof steer !== 'number') {
    return res.status(400).json({ success: false, message: 'Invalid command payload' });
  }

  const result = carlaService.applyControl({ throttle, brake, steer });
  res.json(result);
}

/**
 * POST /api/control/emergency-stop
 */
function emergencyStop(req, res) {
  const result = carlaService.emergencyStop();
  res.json(result);
}

module.exports = { sendCommand, emergencyStop };
