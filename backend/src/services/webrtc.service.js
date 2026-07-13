/**
 * WebRTC Service
 * Manages WebRTC signaling state for each peer connection.
 * Phase 1: Stub — tracks peer sessions.
 * Phase 2: Will broker SDP offers/answers and ICE candidates between browser and CARLA stream.
 */

const sessions = new Map(); // sessionId → { operatorSocketId, vehicleSocketId }

function createSession(sessionId, operatorSocketId) {
  sessions.set(sessionId, { operatorSocketId, vehicleSocketId: null, created: Date.now() });
  return sessions.get(sessionId);
}

function attachVehicle(sessionId, vehicleSocketId) {
  if (!sessions.has(sessionId)) return null;
  sessions.get(sessionId).vehicleSocketId = vehicleSocketId;
  return sessions.get(sessionId);
}

function getSession(sessionId) {
  return sessions.get(sessionId) || null;
}

function removeSession(sessionId) {
  sessions.delete(sessionId);
}

function listSessions() {
  return Array.from(sessions.entries()).map(([id, s]) => ({ id, ...s }));
}

module.exports = { createSession, attachVehicle, getSession, removeSession, listSessions };
