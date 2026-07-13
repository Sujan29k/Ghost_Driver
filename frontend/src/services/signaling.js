/**
 * WebRTC Signaling Service
 * Wraps signaling socket events to simplify hook usage.
 * Phase 1 scaffold — full SDP/ICE exchange in Phase 2.
 */
import { socket } from './socket';

export function startSession() {
  socket.emit('webrtc:start-session');
}

export function sendOffer(sessionId, sdp) {
  socket.emit('webrtc:offer', { sessionId, sdp });
}

export function sendAnswer(sessionId, sdp) {
  socket.emit('webrtc:answer', { sessionId, sdp });
}

export function sendIceCandidate(sessionId, candidate) {
  socket.emit('webrtc:ice-candidate', { sessionId, candidate });
}

export function endSession(sessionId) {
  socket.emit('webrtc:end-session', { sessionId });
}

export default { startSession, sendOffer, sendAnswer, sendIceCandidate, endSession };
