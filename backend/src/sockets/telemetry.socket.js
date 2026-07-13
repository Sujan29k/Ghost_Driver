/**
 * Telemetry Socket Handler
 * Pushes live telemetry to all connected operator clients at ~5 Hz.
 */

const carlaService = require('../services/carla.service');
const latencyService = require('../services/latency.service');
const { ingestTelemetry } = require('../controllers/telemetry.controller');

let _io = null;
let _fps = 0;
let _frameCount = 0;
let _fpsInterval = null;

function init(io) {
  _io = io;

  // Track FPS of telemetry pushes
  _fpsInterval = setInterval(() => {
    _fps = _frameCount;
    _frameCount = 0;
  }, 1000);

  // Subscribe to CARLA telemetry
  carlaService.onTelemetry((data) => {
    _frameCount++;
    const enriched = {
      ...data,
      fps: _fps,
      latency: latencyService.getAverageLatency(),
      packetLoss: latencyService.getPacketLoss(),
      networkQuality: latencyService.getNetworkQuality(),
    };
    ingestTelemetry(enriched);
    if (_io) _io.emit('telemetry:update', enriched);
  });
}

function registerHandlers(socket) {
  // Ping/pong for latency measurement
  socket.on('ping:measure', (sentAt) => {
    const latency = Date.now() - sentAt;
    latencyService.recordLatency(latency);
    socket.emit('pong:measure', { sentAt, receivedAt: Date.now(), latency });
  });

  // Request a snapshot of the latest telemetry on connect
  socket.on('telemetry:request', () => {
    socket.emit('telemetry:update', {
      speed: 0,
      fps: 0,
      latency: 0,
      packetLoss: 0,
      networkQuality: 'excellent',
      carlaConnected: carlaService.isConnected(),
      timestamp: Date.now(),
    });
  });
}

module.exports = { init, registerHandlers };
