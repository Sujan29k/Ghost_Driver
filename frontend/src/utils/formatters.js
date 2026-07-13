/**
 * Formatting utilities for telemetry display.
 */

/**
 * Format speed to km/h string.
 * @param {number} kph
 */
export function formatSpeed(kph) {
  return `${Math.round(kph)}`;
}

/**
 * Format latency with color class.
 * @param {number} ms
 * @returns {{ label: string, colorClass: string }}
 */
export function formatLatency(ms) {
  const label = `${Math.round(ms)}ms`;
  if (ms < 50)  return { label, colorClass: 'text-ghost-success' };
  if (ms < 100) return { label, colorClass: 'text-yellow-400' };
  if (ms < 200) return { label, colorClass: 'text-orange-400' };
  return { label, colorClass: 'text-ghost-danger' };
}

/**
 * Format packet loss percentage.
 * @param {number} pct 0-100
 */
export function formatPacketLoss(pct) {
  return `${pct.toFixed(1)}%`;
}

/**
 * Format heading to compass direction.
 * @param {number} deg 0-360
 */
export function formatHeading(deg) {
  const dirs = ['N','NE','E','SE','S','SW','W','NW'];
  return dirs[Math.round(deg / 45) % 8];
}

/**
 * Network quality to display info.
 * @param {'excellent'|'good'|'poor'|'critical'} quality
 * @returns {{ label: string, colorClass: string, barColor: string }}
 */
export function formatNetworkQuality(quality) {
  const map = {
    excellent: { label: 'EXCELLENT', colorClass: 'text-ghost-success', barColor: 'bg-ghost-success' },
    good:      { label: 'GOOD',      colorClass: 'text-blue-400',       barColor: 'bg-blue-400' },
    poor:      { label: 'POOR',      colorClass: 'text-yellow-400',     barColor: 'bg-yellow-400' },
    critical:  { label: 'CRITICAL',  colorClass: 'text-ghost-danger',   barColor: 'bg-ghost-danger' },
  };
  return map[quality] || map.excellent;
}

/**
 * Format FPS.
 * @param {number} fps
 * @returns {{ label: string, colorClass: string }}
 */
export function formatFPS(fps) {
  const label = `${Math.round(fps)}`;
  if (fps >= 30) return { label, colorClass: 'text-ghost-success' };
  if (fps >= 15) return { label, colorClass: 'text-yellow-400' };
  return { label, colorClass: 'text-ghost-danger' };
}
