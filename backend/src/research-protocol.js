const modes = ['STOPPED', 'AUTONOMOUS', 'TAKEOVER_REQUESTED', 'MANUAL', 'EMERGENCY_STOP'];
const methods = ['off', 'raft', 'farneback'];
const views = ['compare', 'delayed', 'predicted', 'reference'];
const scenarios = ['none', 'normal', 'rain', 'landslide', 'flood', 'combined'];
const text = (v, n = 160) => typeof v === 'string' ? v.slice(0, n) : '';
const number = (v, max = 1e12) => Number.isFinite(v) && Math.abs(v) <= max ? v : null;
const choice = (v, allowed, fallback) => allowed.includes(v) ? v : fallback;

function validateCommand(action, data = {}) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('Invalid operation data');
  const require = (condition, message) => { if (!condition) throw new Error(message); };
  switch (action) {
    case 'mode':
      require(['STOPPED', 'MANUAL', 'AUTONOMOUS'].includes(data.mode), 'Invalid driving mode');
      return { mode: data.mode };
    case 'direction':
      require(['forward', 'reverse'].includes(data.direction), 'Invalid direction');
      return { direction: data.direction };
    case 'video':
      require([0, 100, 200, 500, 800].includes(data.delayMs) && methods.includes(data.method) && views.includes(data.view)
        && (data.reference === undefined || typeof data.reference === 'boolean'), 'Invalid comparison settings');
      return { delayMs: data.delayMs, method: data.method, view: data.view, reference: data.reference === true };
    case 'route':
      require(['straight', 'left', 'right'].includes(data.route), 'Invalid route');
      return { route: data.route };
    case 'scenario':
      require(data.operation === undefined || ['start', 'reset'].includes(data.operation), 'Invalid scenario operation');
      require(scenarios.includes(data.name) && [1, 2, 3].includes(data.severity)
        && Number.isInteger(data.seed) && data.seed >= 0 && data.seed <= 2147483647
        && ['partial', 'full'].includes(data.blockage), 'Invalid scenario settings');
      const weather = {};
      const bounds = { precipitation: [0, 100], wetness: [0, 100], puddles: [0, 100], fogDensity: [0, 100],
        sunAltitude: [-90, 90], friction: [.05, 2] };
      for (const [key, value] of Object.entries(data.weather || {})) {
        require(bounds[key] && Number.isFinite(value) && value >= bounds[key][0] && value <= bounds[key][1], 'Invalid scenario weather setting');
        weather[key] = value;
      }
      return { name: data.name, severity: data.severity, seed: data.seed, blockage: data.blockage, weather,
        operation: data.operation || 'reset' };
    case 'buffer':
      require(data.operation === 'clear', 'Invalid buffer operation');
      return { operation: 'clear' };
    case 'policy': {
      const bounds = { stallSeconds: [3, 120], deviationMeters: [1, 30], deviationSeconds: [.5, 30],
        weatherThreshold: [1, 100], hazardDistance: [3, 50], blockedSeconds: [.5, 30] };
      require(Object.keys(data).length > 0, 'Specify a takeover threshold');
      const settings = {};
      for (const [key, value] of Object.entries(data)) {
        require(bounds[key] && Number.isFinite(value) && value >= bounds[key][0] && value <= bounds[key][1], 'Invalid takeover threshold');
        settings[key] = value;
      }
      return settings;
    }
    case 'trial':
      require(['start', 'stop'].includes(data.operation), 'Invalid trial operation');
      if (data.operation === 'stop') return { operation: 'stop', outcome: choice(data.outcome, ['completed', 'aborted', 'blocked'], 'unspecified') };
      require(typeof data.label === 'string' && data.label.length <= 80 && typeof data.saveFrames === 'boolean'
        && Number.isInteger(data.order) && data.order > 0 && data.order <= 10000, 'Invalid trial settings');
      return { operation: 'start', label: data.label, saveFrames: data.saveFrames, order: data.order };
    default: throw new Error('Unknown research operation');
  }
}

function sanitizeComparison(c) {
  if (!c || typeof c !== 'object') return null;
  return { delayMs: [0, 100, 200, 500, 800].includes(c.delayMs) ? c.delayMs : null, method: choice(c.method, methods, 'off'), view: choice(c.view, views, 'compare'),
    reference: c.reference === true, status: text(c.status, 40), predictionReady: c.predictionReady === true,
    predictionStatus: text(c.predictionStatus, 80), referenceFrame: number(c.referenceFrame), delayedFrame: number(c.delayedFrame),
    previousFrame: number(c.previousFrame), referenceTimestamp: number(c.referenceTimestamp), delayedTimestamp: number(c.delayedTimestamp),
    horizonMs: number(c.horizonMs, 2000), intervalMs: number(c.intervalMs, 1000), predictionMs: number(c.predictionMs, 60000),
    processingMs: number(c.processingMs, 60000) };
}

function sanitizeResearch(r) {
  if (!r || r.version !== 1 || !modes.includes(r.mode) || typeof r.stopped !== 'boolean'
    || (r.stopped === ['MANUAL', 'AUTONOMOUS'].includes(r.mode))
    || !Number.isInteger(r.commandId) || !Number.isInteger(r.generation)) return null;
  const s = r.scenario || {}, route = r.route || {}, trial = r.trial || {};
  const strings = (values) => Array.isArray(values) ? values.slice(0, 8).map(v => text(v, 200)) : [];
  const policy = {};
  for (const key of ['stallSeconds', 'deviationMeters', 'deviationSeconds', 'weatherThreshold', 'hazardDistance', 'blockedSeconds']) {
    policy[key] = number(r.policy?.[key], 120);
  }
  return { version: 1, mode: r.mode, stopped: r.stopped, commandId: r.commandId, generation: r.generation,
    direction: r.direction === 'reverse' ? 'reverse' : 'forward', directionLimitKmh: number(r.directionLimitKmh, 5), reason: text(r.reason),
    takeover: r.takeover ? { reason: text(r.takeover.reason), source: choice(r.takeover.source,
      ['scripted', 'simulator-state', 'sensor', 'operator', 'learned-model'], 'unknown'), triggerNs: number(r.takeover.triggerNs, 1e20) } : null,
    route: { name: text(route.name, 30), lengthMeters: number(route.lengthMeters), progress: number(route.progress),
      deviation: number(route.deviation), finished: route.finished === true },
    scenario: { name: choice(s.name, scenarios, 'none'), active: s.active === true, severity: number(s.severity, 3),
      seed: number(s.seed, 2147483647), blockage: s.blockage === 'full' ? 'full' : 'partial',
      warnings: strings(s.warnings), effects: strings(s.effects), friction: number(s.friction, 100),
      weather: Object.fromEntries(['precipitation', 'wetness', 'precipitation_deposits', 'fog_density', 'sun_altitude_angle'].map(key => [key, number(s.weather?.[key], 100)])) },
    video: r.video ? sanitizeComparison(r.video) : null, policy,
    trial: { active: trial.active === true, id: text(trial.id, 80), dropped: number(trial.dropped),
      error: text(trial.error, 80), saveFrames: trial.saveFrames === true } };
}
module.exports = { validateCommand, sanitizeResearch, sanitizeComparison };
