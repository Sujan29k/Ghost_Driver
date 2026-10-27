const { randomUUID } = require('node:crypto');

function perceptionTelemetry(data) {
  const p = data?.perception;
  const count = (n) => Number.isInteger(n) && n >= 0 && n <= 10000 ? n : 0;
  const duration = (n) => Number.isFinite(n) && n >= 0 ? Math.min(n, 60000) : null;
  const method = ['raft', 'farneback'].includes(p?.prediction?.method) ? p.prediction.method : 'off';
  return {
    perception: { enabled: p?.enabled === true, fresh: p?.fresh === true,
      objects: count(p?.objects), warning: p?.warning === true, flow: p?.flow === true,
      inferenceMs: duration(p?.inferenceMs),
      prediction: { method, ready: method !== 'off' && p?.prediction?.ready === true,
        horizonMs: Number.isInteger(p?.prediction?.horizonMs) && p.prediction.horizonMs > 0 && p.prediction.horizonMs <= 800
          ? p.prediction.horizonMs : null,
        inferenceMs: duration(p?.prediction?.inferenceMs) } },
    traffic: { vehicles: count(data?.traffic?.vehicles), bicycles: count(data?.traffic?.bicycles),
      pedestrians: count(data?.traffic?.pedestrians) },
  };
}

function createVehicleHub(io, { commandTimeout = 750, providerTimeout = 6000, frameTimeout = 5000, config } = {}) {
  const vehicles = new Map();
  const operators = new Map();
  const sessions = new Map();
  const publicVehicle = (v) => ({ id: v.id, name: v.name, mode: v.mode, busy: !!v.owner, ready: v.ready, phase: v.phase });
  const publish = () => io.emit('vehicles:list', [...vehicles.values()].map(publicVehicle));
  const owned = (socket) => vehicles.get(operators.get(socket.id));
  const reply = (ack, result) => { if (typeof ack === 'function') ack(result); };
  function sendControl(v, control, reason) {
    v.commandId += 1;
    io.to(v.id).emit('control:apply', { ...control, emergency: v.emergency, commandId: v.commandId,
      serverTimestamp: Date.now(), timeoutMs: commandTimeout, reason });
  }
  function stop(v, reason) {
    sendControl(v, { throttle: 0, brake: 1, steer: 0 }, reason);
    v.lastCommand = 0;
  }
  function latch(v, reason) {
    v.emergency = true;
    if (v.owner) io.to(v.owner).emit('vehicle:emergency', { active: true });
    stop(v, reason);
  }
  function stopStream(v, reason = 'Stream stopped') {
    const session = sessions.get(v.id);
    if (!session) return;
    sessions.delete(v.id);
    for (const id of [v.id, session.operatorId]) io.to(id).emit('stream:stopped', { sessionId: session.id, reason });
    latch(v, reason);
  }
  function release(socketId, reason) {
    const v = vehicles.get(operators.get(socketId));
    if (!v) return;
    stopStream(v, reason);
    stop(v, reason);
    v.owner = null;
    operators.delete(socketId);
    io.to(socketId).emit('vehicle:released', { reason });
    publish();
  }
  function removeVehicle(id, reason) {
    const v = vehicles.get(id);
    if (!v) return;
    if (v.owner) release(v.owner, reason);
    vehicles.delete(id);
    publish();
  }
  const timer = setInterval(() => {
    const now = Date.now();
    for (const v of vehicles.values()) {
      if (now - v.lastSeen > providerTimeout) { removeVehicle(v.id, 'Vehicle telemetry timed out'); continue; }
      if (v.lastCommand && now - v.lastCommand > commandTimeout) latch(v, 'Control timeout');
      const session = sessions.get(v.id);
      if (session?.ready && now - session.lastFrame > frameTimeout) stopStream(v, 'Video frames timed out');
      if (session && !session.ready && now - session.created > 45000) stopStream(v, 'Video connection timed out');
    }
  }, 100);
  timer.unref();

  function register(socket) {
    socket.emit('vehicles:list', [...vehicles.values()].map(publicVehicle));
    socket.on('rtc:config', (_data, ack) => reply(ack, { success: true, iceServers: config.iceServers, allowDemo: config.allowDemo }));
    socket.on('vehicles:request', () => socket.emit('vehicles:list', [...vehicles.values()].map(publicVehicle)));
    socket.on('ping:measure', (_data, ack) => reply(ack, { serverTimestamp: Date.now() }));
    socket.on('vehicle:join', (data, ack) => {
      if (socket.data.role !== 'sender') return reply(ack, { success: false, message: 'Sender token required' });
      if (data?.mode === 'mock' && !config.allowDemo) return reply(ack, { success: false, message: 'Demo mode is disabled' });
      if (!data || !['mock', 'carla'].includes(data.mode)) return reply(ack, { success: false, message: 'Provider mode must be mock or carla' });
      if (operators.has(socket.id)) return reply(ack, { success: false, message: 'Release your vehicle before becoming a provider' });
      if (!vehicles.has(socket.id)) vehicles.set(socket.id, { id: socket.id, name: String(data.name || 'Vehicle').slice(0, 80),
        mode: data.mode, ready: data.mode === 'mock', phase: data.mode === 'mock' ? 'ready' : 'starting', owner: null, emergency: true, telemetry: null, lastSeen: Date.now(), lastCommand: 0, commandId: 0, sequence: -1 });
      publish();
      reply(ack, { success: true, vehicleId: socket.id });
    });
    socket.on('vehicle:connect', (data, ack) => {
      if (socket.data.role !== 'dashboard') return reply(ack, { success: false, message: 'Dashboard token required' });
      const v = vehicles.get(data?.vehicleId);
      if (!v || vehicles.has(socket.id)) return reply(ack, { success: false, message: 'Vehicle unavailable' });
      if (v.owner && v.owner !== socket.id) return reply(ack, { success: false, message: 'Vehicle is already controlled by another operator' });
      if (operators.get(socket.id) && operators.get(socket.id) !== v.id) release(socket.id, 'Vehicle changed');
      v.owner = socket.id;
      v.sequence = -1;
      operators.set(socket.id, v.id);
      latch(v, 'Operator connected');
      reply(ack, { success: true, vehicle: publicVehicle(v), emergency: v.emergency });
      if (v.telemetry) socket.emit('telemetry:update', v.telemetry);
      publish();
    });
    socket.on('vehicle:disconnect', (_data, ack) => { release(socket.id, 'Operator disconnected'); reply(ack, { success: true }); });
    socket.on('control:direct', (data, ack) => {
      const v = owned(socket);
      if (!v || !data) return reply(ack, { success: false, message: 'Connect to a vehicle first' });
      const valid = ['throttle', 'brake', 'steer'].every((key) => Number.isFinite(data[key])) &&
        data.throttle >= 0 && data.throttle <= 1 && data.brake >= 0 && data.brake <= 1 && Math.abs(data.steer) <= 1 &&
        Number.isSafeInteger(data.sequence) && data.sequence > v.sequence;
      if (!valid) return reply(ack, { success: false, message: 'Invalid or stale control' });
      if (!sessions.get(v.id)?.ready) return reply(ack, { success: false, message: 'Received video required for controls' });
      if (v.emergency) return reply(ack, { success: false, message: 'Emergency stop is active' });
      v.sequence = data.sequence;
      v.lastCommand = Date.now();
      sendControl(v, { throttle: data.brake > 0 ? 0 : data.throttle, brake: data.brake, steer: data.steer }, 'Operator command');
      reply(ack, { success: true, commandId: v.commandId });
    });
    socket.on('control:emergency', (_data, ack) => {
      const v = owned(socket);
      if (!v) return reply(ack, { success: false, message: 'No owned vehicle' });
      v.emergency = true;
      stop(v, 'Emergency stop');
      socket.emit('vehicle:emergency', { active: true });
      reply(ack, { success: true });
    });
    socket.on('control:resume', (_data, ack) => {
      const v = owned(socket);
      if (!v) return reply(ack, { success: false, message: 'No owned vehicle' });
      if (!sessions.get(v.id)?.ready) return reply(ack, { success: false, message: 'Wait for received video before resuming controls' });
      v.resumedAt = Date.now();
      v.emergency = false;
      stop(v, 'Controls resumed');
      socket.emit('vehicle:emergency', { active: false });
      reply(ack, { success: true });
    });
    socket.on('vehicle:status', (data) => {
      const v = vehicles.get(socket.id);
      if (!v) { if (socket.data.role === 'sender') socket.emit('vehicle:registration-required', {}); return; }
      if (data?.controlsStopped === true && !v.emergency && Date.now() - v.resumedAt > 1000) latch(v, 'Sender safety stop');
      v.lastSeen = Date.now();
      const ready = data?.ready === true;
      // Only known phases cross to the dashboard. Never forward raw exceptions,
      // filesystem paths, backend URLs or sender credentials.
      const phases = ['loading-models', 'connecting-carla', 'spawning-traffic', 'waiting-camera', 'camera-unavailable', 'error'];
      const phase = ready ? 'ready' : phases.includes(data?.phase) ? data.phase : 'starting';
      if (ready !== v.ready || phase !== v.phase) {
        const lostCamera = v.ready && !ready;
        v.ready = ready;
        v.phase = phase;
        if (lostCamera) { stopStream(v, 'CARLA camera unavailable'); latch(v, 'CARLA unavailable'); }
        publish();
      }
    });
    socket.on('vehicle:telemetry', (data) => {
      const v = vehicles.get(socket.id);
      if (!v) { socket.emit('vehicle:registration-required', {}); return; }
      if (!data || !['speed', 'throttle', 'brake', 'steer', 'heading'].every((key) => Number.isFinite(data[key]))) return;
      v.lastSeen = Date.now();
      v.telemetry = { vehicleId: v.id, mode: v.mode, receivedAt: Date.now(), emergency: v.emergency,
        speed: data.speed, throttle: data.throttle, brake: data.brake, steer: data.steer, heading: data.heading,
        gear: String(data.gear || 'N').slice(0, 8), frameId: Number.isFinite(data.frameId) ? data.frameId : null,
        simulationTimestamp: Number.isFinite(data.simulationTimestamp) ? data.simulationTimestamp : null,
        ...perceptionTelemetry(data) };
      if (v.owner) io.to(v.owner).emit('telemetry:update', v.telemetry);
    });
    socket.on('stream:request', (data, ack) => {
      const v = owned(socket);
      if (!v || v.id !== data?.vehicleId) return reply(ack, { success: false, message: 'Connect to this vehicle first' });
      if (!v.ready) return reply(ack, { success: false, message: 'Waiting for CARLA camera frames' });
      const relayOnly = data.relayOnly === true;
      if (relayOnly && !config.iceServers.some((server) => /^turns?:/.test(server.urls))) {
        return reply(ack, { success: false, message: 'Configure TURN on the backend before testing TURN' });
      }
      stopStream(v, 'Stream restarted');
      latch(v, 'Video connecting');
      const session = { id: randomUUID(), operatorId: socket.id, created: Date.now(), ready: false };
      sessions.set(v.id, session);
      socket.emit('stream:starting', { sessionId: session.id, vehicleId: v.id, relayOnly });
      io.to(v.id).emit('stream:start', { sessionId: session.id, operatorId: socket.id, relayOnly });
      reply(ack, { success: true, sessionId: session.id });
    });
    for (const event of ['webrtc:offer', 'webrtc:answer', 'webrtc:ice-candidate']) {
      socket.on(event, (data) => {
        if (!data) return;
        const v = vehicles.get(socket.id) || owned(socket);
        const session = v && sessions.get(v.id);
        if (!session || data.sessionId !== session.id) return;
        const isVehicle = socket.id === v.id;
        if ((event === 'webrtc:offer' && !isVehicle) || (event === 'webrtc:answer' && isVehicle)) return;
        const target = isVehicle ? session.operatorId : v.id;
        if (event !== 'webrtc:ice-candidate' && (typeof data.sdp?.sdp !== 'string' || data.sdp.type !== (event === 'webrtc:offer' ? 'offer' : 'answer'))) return;
        io.to(target).emit(event, { sessionId: session.id, fromId: socket.id,
          ...(event === 'webrtc:ice-candidate' ? { candidate: data.candidate } : { sdp: data.sdp }) });
      });
    }
    socket.on('stream:ready', (data) => {
      const v = owned(socket);
      const session = v && sessions.get(v.id);
      if (session && session.id === data?.sessionId) { session.ready = true; session.lastFrame = Date.now(); }
    });
    socket.on('stream:stop', () => { const v = owned(socket); if (v) stopStream(v); });
    socket.on('stream:error', (data) => {
      const v = vehicles.get(socket.id) || owned(socket);
      if (v && sessions.get(v.id)?.id === data?.sessionId) stopStream(v, String(data.message || 'Video connection failed').slice(0, 160));
    });
    socket.on('disconnect', () => {
      release(socket.id, 'Operator connection lost');
      removeVehicle(socket.id, 'Vehicle connection lost');
    });
  }
  return { register, close: () => clearInterval(timer), health: () => ({
    vehicles: [...vehicles.values()].map(publicVehicle), sessions: sessions.size,
    prediction: 'provider', telemetry: 'provider',
  }) };
}
module.exports = { createVehicleHub };
