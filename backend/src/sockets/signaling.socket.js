/**
 * WebRTC Signaling Socket Handler — Rewritten for Phase 2 (webcam test)
 *
 * Roles:
 *   - "vehicle" socket: the vehicle-sim page (Tab 2) — HAS the camera, sends offer
 *   - "operator" socket: the dashboard (Tab 1) — WANTS the stream, sends answer
 *
 * Flow:
 *   1. Vehicle joins  → server stores its socketId, broadcasts vehicle:available
 *   2. Operator clicks "Start Stream" → sends stream:request with vehicleId
 *   3. Server tells vehicle to start → vehicle grabs webcam, creates offer
 *   4. Offer relayed operator → operator creates answer → answer relayed to vehicle
 *   5. ICE candidates exchanged both ways
 *   6. P2P video flows browser-to-browser
 */

const { v4: uuidv4 } = require('uuid');

// Track registered vehicle sockets: socketId → { id, name }
const vehicles = new Map();

function registerHandlers(socket, io) {
  // Let newly connected dashboards discover vehicles that joined earlier.
  for (const vehicle of vehicles.values()) {
    socket.emit('vehicle:available', vehicle);
  }

  // ── VEHICLE SIDE ────────────────────────────────────────────────────────

  /** Vehicle simulator page announces itself */
  socket.on('vehicle:join', ({ name = 'Vehicle-Sim' } = {}) => {
    vehicles.set(socket.id, { id: socket.id, name });
    // Tell all operators a vehicle is available
    io.emit('vehicle:available', { id: socket.id, name });
    socket.emit('vehicle:join:ack', { success: true });
    console.log(`[Signal] 🚗 Vehicle joined: ${socket.id} (${name})`);
  });

  // ── OPERATOR SIDE ───────────────────────────────────────────────────────

  /** Operator requests a live stream from a specific vehicle */
  socket.on('stream:request', ({ vehicleId } = {}) => {
    if (!vehicleId || !vehicles.has(vehicleId)) {
      socket.emit('stream:error', { message: 'Vehicle not available' });
      return;
    }
    const sessionId = uuidv4();
    // Tell operator stream is incoming
    socket.emit('stream:starting', { sessionId, vehicleId });
    // Tell vehicle to start — pass operator's socketId so it knows where to send offer
    io.to(vehicleId).emit('stream:start', { sessionId, operatorId: socket.id });
    console.log(`[Signal] 📡 Stream starting: session=${sessionId.slice(0, 8)} op=${socket.id.slice(0, 6)} vehicle=${vehicleId.slice(0, 6)}`);
  });

  // ── SDP RELAY (both directions) ─────────────────────────────────────────

  /** Vehicle → Operator: relay SDP offer */
  socket.on('webrtc:offer', ({ sessionId, sdp, targetId }) => {
    if (!targetId) return;
    io.to(targetId).emit('webrtc:offer', { sessionId, sdp, fromId: socket.id });
    console.log(`[Signal] 📨 Offer → ${targetId.slice(0, 6)}`);
  });

  /** Operator → Vehicle: relay SDP answer */
  socket.on('webrtc:answer', ({ sessionId, sdp, targetId }) => {
    if (!targetId) return;
    io.to(targetId).emit('webrtc:answer', { sessionId, sdp });
    console.log(`[Signal] 📩 Answer → ${targetId.slice(0, 6)}`);
  });

  /** Relay ICE candidates both ways */
  socket.on('webrtc:ice-candidate', ({ sessionId, candidate, targetId }) => {
    if (!targetId) return;
    io.to(targetId).emit('webrtc:ice-candidate', { sessionId, candidate });
  });

  /** Stop stream */
  socket.on('stream:stop', ({ targetId } = {}) => {
    if (targetId) io.to(targetId).emit('stream:stopped');
  });

  // ── CLEANUP ─────────────────────────────────────────────────────────────

  socket.on('disconnect', () => {
    if (vehicles.has(socket.id)) {
      const v = vehicles.get(socket.id);
      vehicles.delete(socket.id);
      io.emit('vehicle:unavailable', { id: socket.id, name: v.name });
      console.log(`[Signal] 🔴 Vehicle disconnected: ${socket.id} (${v.name})`);
    }
  });
}

module.exports = { registerHandlers };
