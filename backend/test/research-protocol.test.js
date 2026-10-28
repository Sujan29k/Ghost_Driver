const { test } = require('node:test');
const assert = require('node:assert/strict');
const { validateCommand, sanitizeResearch, sanitizeComparison } = require('../src/research-protocol');

test('research command schema bounds direction, delay, scenarios, thresholds and trials', () => {
  assert.deepEqual(validateCommand('direction', { direction: 'reverse' }), { direction: 'reverse' });
  assert.throws(() => validateCommand('direction', { direction: 'negative-throttle' }));
  assert.deepEqual(validateCommand('video', { delayMs: 800, method: 'raft', view: 'compare', reference: true }),
    { delayMs: 800, method: 'raft', view: 'compare', reference: true });
  assert.throws(() => validateCommand('video', { delayMs: 900, method: 'raft', view: 'compare' }));
  assert.throws(() => validateCommand('scenario', { name: 'flood', severity: 9, seed: 1, blockage: 'partial' }));
  assert.throws(() => validateCommand('scenario', { name: 'rain', severity: 1, seed: 1, blockage: 'partial', weather: { friction: 4 } }));
  assert.throws(() => validateCommand('policy', { weatherThreshold: 101 }));
  assert.throws(() => validateCommand('trial', { operation: 'start', label: 'x', saveFrames: true, order: 0 }));
});

test('research telemetry removes untrusted fields and never invents learned confidence', () => {
  const state = sanitizeResearch({ version: 1, mode: 'TAKEOVER_REQUESTED', stopped: true, commandId: 5, generation: 2,
    takeover: { reason: 'Rain threshold', source: 'scripted', confidence: .99, triggerNs: 42 },
    scenario: { name: 'flood', warnings: ['FLOOD APPROXIMATION'], actors: ['private'] },
    video: { delayMs: 200, method: 'raft', horizonMs: 200, secret: 'drop' }, private: 'drop' });
  assert.equal(state.takeover.source, 'scripted');
  assert.equal(Object.hasOwn(state.takeover, 'confidence'), false);
  assert.equal(Object.hasOwn(state, 'private'), false);
  assert.equal(Object.hasOwn(state.scenario, 'actors'), false);
  assert.equal(sanitizeComparison({ delayMs: 200, token: 'secret' }).token, undefined);
  assert.equal(sanitizeResearch({ version: 2 }), null);
  assert.equal(sanitizeResearch({ version: 1, mode: 'AUTONOMOUS', stopped: true, commandId: 5, generation: 2 }), null);
});
