/**
 * Latency Service
 * Measures round-trip latency and tracks packet statistics.
 * Phase 2: Will feed into AI prediction model.
 */

const measurements = [];
const MAX_MEASUREMENTS = 100;

/**
 * Record a latency measurement (ms).
 * @param {number} ms
 */
function recordLatency(ms) {
  measurements.push({ ts: Date.now(), ms });
  if (measurements.length > MAX_MEASUREMENTS) measurements.shift();
}

/**
 * Get average latency over the last N measurements.
 * @param {number} n
 * @returns {number}
 */
function getAverageLatency(n = 10) {
  const slice = measurements.slice(-n);
  if (!slice.length) return 0;
  return Math.round(slice.reduce((sum, m) => sum + m.ms, 0) / slice.length);
}

/**
 * Get packet loss estimate based on missed pings.
 * Stub: returns 0 until WebRTC/CARLA is integrated.
 * @returns {number} percentage 0–100
 */
function getPacketLoss() {
  return 0;
}

/**
 * Get network quality label.
 * @returns {'excellent'|'good'|'poor'|'critical'}
 */
function getNetworkQuality() {
  const avg = getAverageLatency();
  if (avg < 50) return 'excellent';
  if (avg < 100) return 'good';
  if (avg < 200) return 'poor';
  return 'critical';
}

module.exports = { recordLatency, getAverageLatency, getPacketLoss, getNetworkQuality };
