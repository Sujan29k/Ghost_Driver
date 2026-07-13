/**
 * Telemetry Controller
 * Handles REST requests for telemetry data and system health.
 */

const carlaService = require('../services/carla.service');
const latencyService = require('../services/latency.service');
const webrtcService = require('../services/webrtc.service');

// In-memory telemetry store (last 500 readings)
const history = [];
const MAX_HISTORY = 500;

/**
 * Ingest telemetry from CARLA service (called internally by socket handler).
 */
function ingestTelemetry(data) {
  history.push(data);
  if (history.length > MAX_HISTORY) history.shift();
}

/**
 * GET /api/telemetry/latest
 */
function getLatestTelemetry(req, res) {
  const latest = history[history.length - 1] || null;
  res.json({ success: true, data: latest });
}

/**
 * GET /api/telemetry/history?limit=50
 */
function getTelemetryHistory(req, res) {
  const limit = Math.min(parseInt(req.query.limit) || 50, 500);
  res.json({ success: true, data: history.slice(-limit) });
}

/**
 * GET /api/health
 */
function getSystemHealth(req, res) {
  res.json({
    success: true,
    timestamp: Date.now(),
    services: {
      carla: { status: carlaService.isConnected() ? 'connected' : 'disconnected' },
      webrtc: { status: 'idle', sessions: webrtcService.listSessions().length },
      yolo: { status: 'offline' },       // Phase 2
      aiPrediction: { status: 'offline' }, // Phase 2
      network: {
        quality: latencyService.getNetworkQuality(),
        avgLatency: latencyService.getAverageLatency(),
        packetLoss: latencyService.getPacketLoss(),
      },
    },
  });
}

module.exports = { getLatestTelemetry, getTelemetryHistory, getSystemHealth, ingestTelemetry };
