/**
 * Telemetry Socket Handler
 * Pushes live telemetry to all connected operator clients at ~5 Hz.
 */

const carlaService = require('../services/carla.service');
const latencyService = require('../services/latency.service');
const { ingestTelemetry, ingestPerception } = require('../controllers/telemetry.controller');

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

  // Real CARLA / Python bridge telemetry
  socket.on('vehicle:telemetry', (data) => {
    if (!data || typeof data !== 'object') return;
    const normalized = {
      ...data,
      speed: data.speed ?? 0,
      throttle: data.throttle ?? 0,
      brake: data.brake ?? 0,
      steer: data.steer ?? 0,
      gear: data.gear ?? 'P',
      heading: data.heading ?? 0,
      carlaConnected: data.carlaConnected ?? true,
      timestamp: data.timestamp ?? Date.now(),
    };
    carlaService.ingestTelemetry(normalized);
  });

  socket.on('vehicle:perception', (data) => {
    if (!data || typeof data !== 'object') return;
    const perception = {
      modelLoaded: Boolean(data.modelLoaded),
      detections: Array.isArray(data.detections) ? data.detections : [],
      inferenceMs: data.inferenceMs ?? null,
      predictionReady: Boolean(data.predictionReady),
      predictionHorizonMs: data.predictionHorizonMs ?? null,
      latencyMs: data.latencyMs ?? null,
      cameraDelayMs: data.cameraDelayMs ?? null,
      controlDelayMs: data.controlDelayMs ?? null,
      predictionMethod: data.predictionMethod ?? 'Farneback',
      predictionMetrics: data.predictionMetrics ?? null,
      timestamp: data.timestamp ?? Date.now(),
    };
    ingestPerception(perception);
    if (_io) _io.emit('perception:update', perception);
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
