const { test } = require('node:test');
const assert = require('node:assert/strict');
const { io } = require('../../frontend/node_modules/socket.io-client');
const { createServer } = require('../src/server');
const { loadConfig } = require('../src/config');
const config = loadConfig({ DASHBOARD_TOKEN: 'test-dashboard-token-'.repeat(3), SENDER_TOKEN: 'test-sender-token-'.repeat(3) });
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
function event(socket, name, predicate = () => true) {
  return new Promise((resolve, reject) => {
    const handler = (data) => { if (predicate(data)) { clearTimeout(timer); socket.off(name, handler); resolve(data); } };
    const timer = setTimeout(() => { socket.off(name, handler); reject(new Error(`Timed out waiting for ${name}`)); }, 2500);
    socket.on(name, handler);
  });
}
const request = (socket, name, data = {}) => new Promise((resolve, reject) => socket.timeout(2000).emit(name, data, (error, result) => error ? reject(error) : resolve(result)));
async function fixture(t, options) {
  const app = createServer({ config, ...options });
  await new Promise((resolve) => app.server.listen(0, '127.0.0.1', resolve));
  const url = `http://127.0.0.1:${app.server.address().port}`;
  const clients = [];
  t.after(async () => { for (const socket of clients) socket.disconnect(); await app.close(); });
  const connect = async (role = 'dashboard') => {
    const socket = io(url, { autoConnect: false, auth: { role, token: config.tokens[role] }, transports: ['websocket'], forceNew: true });
    clients.push(socket);
    const connected = event(socket, 'connect'); socket.connect(); await connected;
    return socket;
  };
  const provider = await connect('sender');
  assert.equal((await request(provider, 'vehicle:join', { name: 'Test CARLA', mode: 'carla' })).success, true);
  provider.emit('vehicle:status', { ready: true });
  const operator = await connect();
  return { ...app, url, provider, operator, connect };
}
const telemetry = { speed: 20, throttle: 0.4, brake: 0, steer: 0.2, heading: 45, gear: '2', frameId: 42, simulationTimestamp: 2.1 };

test('late discovery, exclusive ownership, actual telemetry and truthful health', async (t) => {
  const f = await fixture(t);
  const discovered = event(f.operator, 'vehicles:list'); f.operator.emit('vehicles:request');
  assert.equal((await discovered)[0].id, f.provider.id);
  assert.equal((await request(f.operator, 'vehicle:connect', { vehicleId: f.provider.id })).success, true);
  const other = await f.connect();
  assert.equal((await request(other, 'vehicle:connect', { vehicleId: f.provider.id })).success, false);
  const received = event(f.operator, 'telemetry:update'); f.provider.emit('vehicle:telemetry', telemetry);
  assert.equal((await received).frameId, 42);
  const health = await (await fetch(`${f.url}/api/health`)).json();
  assert.deepEqual(health, { success: true }); assert.equal(f.hub.health().vehicles.length, 1);
  assert.equal((await fetch(`${f.url}/api/control/command`, { method: 'POST' })).status, 405);
});

test('full controls validate ranges and sequence; emergency stop remains latched until resume', async (t) => {
  const f = await fixture(t);
  await request(f.operator, 'vehicle:connect', { vehicleId: f.provider.id });
  await readyAndResume(f);
  const command = event(f.provider, 'control:apply', (d) => d.reason === 'Operator command');
  assert.equal((await request(f.operator, 'control:direct', { throttle: 0.8, brake: 0, steer: -0.5, sequence: 1 })).success, true);
  const data = await command; assert.equal(data.throttle, 0.8); assert.equal(data.steer, -0.5);
  for (const invalid of [null, { throttle: 2, brake: 0, steer: 0, sequence: 2 }, { throttle: 1, brake: 0, steer: 0, sequence: 1 }]) {
    assert.equal((await request(f.operator, 'control:direct', invalid)).success, false);
  }
  const stop = event(f.provider, 'control:apply', (d) => d.emergency);
  await request(f.operator, 'control:emergency'); assert.equal((await stop).brake, 1);
  assert.equal((await request(f.operator, 'control:direct', { throttle: 1, brake: 0, steer: 0, sequence: 3 })).success, false);
  await request(f.operator, 'control:resume');
  assert.equal((await request(f.operator, 'control:direct', { throttle: 1, brake: 0, steer: 0, sequence: 4 })).success, true);
});

test('signaling is scoped to owned session; restart and disconnect close both peers', async (t) => {
  const f = await fixture(t);
  await request(f.operator, 'vehicle:connect', { vehicleId: f.provider.id });
  const start = event(f.provider, 'stream:start');
  const result = await request(f.operator, 'stream:request', { vehicleId: f.provider.id });
  assert.equal((await start).sessionId, result.sessionId);
  const offer = event(f.operator, 'webrtc:offer');
  f.provider.emit('webrtc:offer', { sessionId: result.sessionId, sdp: { type: 'offer', sdp: 'test' } });
  assert.equal((await offer).fromId, f.provider.id);
  const intruder = await f.connect();
  const forwarded = []; f.provider.on('webrtc:answer', (data) => forwarded.push(data));
  intruder.emit('webrtc:answer', { sessionId: result.sessionId, sdp: { type: 'answer', sdp: 'bad' } });
  f.operator.emit('webrtc:answer', { sessionId: 'old-session', sdp: { type: 'answer', sdp: 'stale' } });
  await delay(50); assert.equal(forwarded.length, 0);
  const answer = event(f.provider, 'webrtc:answer');
  f.operator.emit('webrtc:answer', { sessionId: result.sessionId, sdp: { type: 'answer', sdp: 'valid' } });
  assert.equal((await answer).sdp.sdp, 'valid');
  const stopped = event(f.provider, 'stream:stopped'); f.operator.disconnect();
  assert.equal((await stopped).reason, 'Operator connection lost');
  await delay(20); assert.equal(f.hub.health().sessions, 0); assert.equal(f.hub.health().vehicles[0].busy, false);
});

test('missing controls brake locally at relay; missing provider telemetry releases owner', async (t) => {
  const f = await fixture(t, { commandTimeout: 100, providerTimeout: 600 });
  await request(f.operator, 'vehicle:connect', { vehicleId: f.provider.id });
  await readyAndResume(f);
  const timedOut = event(f.provider, 'control:apply', (data) => data.reason === 'Control timeout');
  await request(f.operator, 'control:direct', { throttle: 1, brake: 0, steer: 0, sequence: 1 });
  assert.equal((await timedOut).brake, 1);
  assert.equal((await request(f.operator, 'control:direct', { throttle: 1, brake: 0, steer: 0, sequence: 2 })).success, false);
  const released = event(f.operator, 'vehicle:released');
  assert.equal((await released).reason, 'Vehicle telemetry timed out');
  assert.equal(f.hub.health().vehicles.length, 0);
  const registerAgain = event(f.provider, 'vehicle:registration-required');
  f.provider.emit('vehicle:telemetry', telemetry); await registerAgain;
});

test('provider disconnect removes discovery and releases operator', async (t) => {
  const f = await fixture(t);
  await request(f.operator, 'vehicle:connect', { vehicleId: f.provider.id });
  const released = event(f.operator, 'vehicle:released'); f.provider.disconnect();
  assert.equal((await released).reason, 'Vehicle connection lost');
  assert.equal(f.hub.health().vehicles.length, 0);
});

async function readyAndResume(f) {
  const { sessionId } = await request(f.operator, 'stream:request', { vehicleId: f.provider.id });
  f.operator.emit('stream:ready', { sessionId });
  assert.equal((await request(f.operator, 'control:resume')).success, true);
  return sessionId;
}

test('authentication rejects absent, invalid, URL-only and wrong-role tokens', async (t) => {
  const f = await fixture(t);
  for (const options of [{}, { auth: { role: 'dashboard', token: 'wrong' } },
    { query: { token: config.tokens.dashboard } }, { auth: { role: 'sender', token: config.tokens.dashboard } }]) {
    const socket = io(f.url, { autoConnect: false, reconnection: false, ...options });
    const rejected = event(socket, 'connect_error'); socket.connect();
    assert.match((await rejected).message, /Authentication failed/); socket.disconnect();
  }
  assert.equal((await request(f.operator, 'vehicle:join', { mode: 'carla' })).success, false);
  assert.equal((await request(f.provider, 'vehicle:connect', { vehicleId: f.provider.id })).success, false);
  const stranger = await f.connect('sender');
  assert.equal((await request(stranger, 'vehicle:join', { mode: 'mock' })).success, false);
});

test('ICE credentials require authentication and TURN-only fails clearly without TURN', async (t) => {
  const f = await fixture(t);
  assert.deepEqual((await request(f.operator, 'rtc:config')).iceServers, []);
  await request(f.operator, 'vehicle:connect', { vehicleId: f.provider.id });
  const result = await request(f.operator, 'stream:request', { vehicleId: f.provider.id, relayOnly: true });
  assert.equal(result.success, false); assert.match(result.message, /Configure TURN/);
});

test('video loss latches controls; a new stream or reconnect never resumes driving', async (t) => {
  const f = await fixture(t);
  await request(f.operator, 'vehicle:connect', { vehicleId: f.provider.id });
  assert.equal((await request(f.operator, 'control:resume')).success, false);
  const sessionId = await readyAndResume(f);
  const stopped = event(f.operator, 'stream:stopped');
  f.provider.emit('stream:error', { sessionId, message: 'network lost' }); await stopped;
  const next = await request(f.operator, 'stream:request', { vehicleId: f.provider.id });
  f.operator.emit('stream:ready', { sessionId: next.sessionId });
  const drive = { throttle: 1, brake: 0, steer: 0, sequence: 100 };
  assert.equal((await request(f.operator, 'control:direct', drive)).success, false);
  await request(f.operator, 'control:resume');
  assert.equal((await request(f.operator, 'control:direct', drive)).success, true);
  await request(f.operator, 'vehicle:disconnect');
  const result = await request(f.operator, 'vehicle:connect', { vehicleId: f.provider.id });
  assert.equal(result.emergency, true);
});

test('sender connected and camera ready are distinct; camera loss stops video', async (t) => {
  const f = await fixture(t);
  await request(f.operator, 'vehicle:connect', { vehicleId: f.provider.id });
  await readyAndResume(f);
  const stopped = event(f.operator, 'stream:stopped');
  f.provider.emit('vehicle:status', { ready: false });
  assert.equal((await stopped).reason, 'CARLA camera unavailable');
  assert.equal(f.hub.health().vehicles[0].ready, false);
  assert.equal((await request(f.operator, 'stream:request', { vehicleId: f.provider.id })).success, false);
});

test('configuration fails closed and passes TURN credentials to both roles', async (t) => {
  assert.throws(() => loadConfig({}), /TOKEN/);
  assert.throws(() => loadConfig({ DASHBOARD_TOKEN: 'a'.repeat(40), SENDER_TOKEN: 'a'.repeat(40) }), /different/);
  const env = { DASHBOARD_TOKEN: config.tokens.dashboard, SENDER_TOKEN: config.tokens.sender, TURN_URL: 'turn:relay.example:3478' };
  assert.throws(() => loadConfig(env), /together/);
  const turnConfig = loadConfig({ ...env, STUN_URL: 'stun:stun.example:3478', TURN_USERNAME: 'test-user', TURN_PASSWORD: 'test-secret' });
  const f = await fixture(t, { config: turnConfig });
  for (const socket of [f.operator, f.provider]) assert.deepEqual((await request(socket, 'rtc:config')).iceServers, turnConfig.iceServers);
  await request(f.operator, 'vehicle:connect', { vehicleId: f.provider.id });
  const starting = event(f.operator, 'stream:starting');
  assert.equal((await request(f.operator, 'stream:request', { vehicleId: f.provider.id, relayOnly: true })).success, true);
  assert.equal((await starting).relayOnly, true);
});


test('missing receiver frame heartbeats closes video and latches brakes', async (t) => {
  const f = await fixture(t, { frameTimeout: 100 });
  await request(f.operator, 'vehicle:connect', { vehicleId: f.provider.id });
  const stopped = event(f.operator, 'stream:stopped');
  await readyAndResume(f);
  assert.equal((await stopped).reason, 'Video frames timed out');
  assert.equal((await request(f.operator, 'control:resume')).success, false);
});
