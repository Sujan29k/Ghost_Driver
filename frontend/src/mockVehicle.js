import { io } from 'socket.io-client';
import { rtcConfig, setIceServers } from './services/rtcConfig';
import './mockVehicle.css';
const socket = io(import.meta.env.VITE_BACKEND_URL || undefined, { autoConnect: false });
document.querySelector('#sender-login').addEventListener('submit', (event) => {
  event.preventDefault();
  const input = document.querySelector('#sender-token');
  socket.auth = { role: 'sender', token: input.value }; input.value = ''; socket.connect();
});
const canvas = document.querySelector('#road');
const ctx = canvas.getContext('2d');
const status = document.querySelector('#status');
const errorNode = document.querySelector('#error');
let control = { throttle: 0, brake: 1, steer: 0 };
let lastCommand = 0, commandId = -1, speed = 0, heading = 0, distance = 0, offset = 0, frameId = 0;
let pc = null, stream = null, sessionId = null, candidates = [];
function brake() { control = { throttle: 0, brake: 1, steer: 0 }; }
function closeStream() {
  const old = pc; pc = null; sessionId = null; candidates = [];
  if (old) { old.onconnectionstatechange = null; old.close(); }
  stream?.getTracks().forEach((track) => track.stop()); stream = null;
  brake();
}
function fail(error, id) {
  if (id !== sessionId) return;
  errorNode.textContent = error.message;
  socket.emit('stream:error', { sessionId: id, message: error.message });
  closeStream();
}
async function register() {
  await new Promise((resolve) => socket.emit('rtc:config', {}, (config) => { setIceServers(config.iceServers); resolve(); }));
  commandId = -1; brake(); errorNode.textContent = '';
  socket.emit('vehicle:join', { name: 'Demo vehicle', mode: 'mock' }, (result) => {
    status.textContent = result.success ? 'Available to dashboard' : result.message;
  });
}
socket.on('connect', register);
socket.on('vehicle:registration-required', register);
socket.on('disconnect', () => { closeStream(); status.textContent = 'Backend disconnected — braking'; });
socket.on('connect_error', (error) => { errorNode.textContent = error.message; });
socket.on('control:apply', (data) => {
  if (data.commandId <= commandId) return;
  commandId = data.commandId; lastCommand = performance.now();
  control = data.emergency ? { throttle: 0, brake: 1, steer: 0 } : data;
});
socket.on('stream:start', async (data) => {
  closeStream(); sessionId = data.sessionId; const id = sessionId;
  try {
    errorNode.textContent = '';
    if (!canvas.captureStream) throw new Error('Canvas video is unavailable; use a current Chrome or Edge browser.');
    const peer = new RTCPeerConnection(rtcConfig()); pc = peer;
    stream = canvas.captureStream(30);
    for (const track of stream.getTracks()) peer.addTrack(track, stream);
    peer.onicecandidate = ({ candidate }) => { if (pc === peer && candidate) socket.emit('webrtc:ice-candidate', { sessionId: id, candidate }); };
    peer.onconnectionstatechange = () => {
      if (pc !== peer) return;
      status.textContent = `Video ${peer.connectionState}`;
      if (['failed', 'disconnected'].includes(peer.connectionState)) fail(new Error('Video connection lost'), id);
    };
    await peer.setLocalDescription(await peer.createOffer());
    if (pc === peer) socket.emit('webrtc:offer', { sessionId: id, sdp: peer.localDescription });
  } catch (error) { fail(error, id); }
});
socket.on('webrtc:answer', async (data) => {
  const peer = pc;
  if (!peer || data.sessionId !== sessionId) return;
  try {
    await peer.setRemoteDescription(data.sdp);
    for (const candidate of candidates) await peer.addIceCandidate(candidate);
    candidates = [];
  } catch (error) { fail(error, data.sessionId); }
});
socket.on('webrtc:ice-candidate', async (data) => {
  if (data.sessionId !== sessionId || !data.candidate) return;
  if (!pc?.remoteDescription) { candidates.push(data.candidate); return; }
  try { await pc.addIceCandidate(data.candidate); } catch (error) { fail(error, data.sessionId); }
});
socket.on('stream:stopped', (data) => { if (data.sessionId === sessionId) { closeStream(); status.textContent = data.reason; } });

function polygon(points, color) {
  ctx.fillStyle = color; ctx.beginPath(); points.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.closePath(); ctx.fill();
}
function draw() {
  const w = canvas.width, h = canvas.height, horizon = 205;
  const sky = ctx.createLinearGradient(0, 0, 0, horizon); sky.addColorStop(0, '#082642'); sky.addColorStop(1, '#99c3c7');
  ctx.fillStyle = sky; ctx.fillRect(0, 0, w, horizon);
  ctx.fillStyle = '#b8dad2'; ctx.beginPath(); ctx.arc(780, 70, 28, 0, Math.PI * 2); ctx.fill();
  polygon([[0, 205], [100, 135], [180, 176], [300, 100], [435, 205]], '#355d62');
  polygon([[380, 205], [590, 123], [715, 168], [850, 112], [960, 205]], '#456c68');
  ctx.fillStyle = '#31594e'; ctx.fillRect(0, horizon, w, h - horizon);
  const center = w / 2 - offset * 140;
  polygon([[w / 2 - 35, horizon], [w / 2 + 35, horizon], [center + 440, h], [center - 440, h]], '#27303c');
  for (const side of [-1, 1]) polygon([[480 + side * 32, horizon], [480 + side * 35, horizon], [center + side * 440, h], [center + side * 428, h]], '#dbe5d4');
  for (let i = 0; i < 12; i++) {
    const z = ((i / 12 + distance * 0.008) % 1);
    const z2 = Math.min(1, z + 0.035);
    const y = horizon + z * z * (h - horizon), y2 = horizon + z2 * z2 * (h - horizon);
    const x = 480 + (center - 480) * z * z;
    const x2 = 480 + (center - 480) * z2 * z2;
    polygon([[x - 2 - z * 4, y], [x + 2 + z * 4, y], [x2 + 2 + z2 * 4, y2], [x2 - 2 - z2 * 4, y2]], '#e4cd87');
  }
  polygon([[150, 540], [240, 495], [720, 495], [810, 540]], '#10212d');
  ctx.fillStyle = '#091a26dd'; ctx.fillRect(18, 18, 390, 68);
  ctx.fillStyle = '#b0f7d1'; ctx.font = 'bold 19px monospace'; ctx.fillText('SYNTHETIC DEMO · NO PREDICTION', 30, 45);
  ctx.fillStyle = '#e2edf3'; ctx.font = '15px monospace'; ctx.fillText(`Frame ${frameId}   ${speed.toFixed(1)} km/h`, 30, 71);
}
let previousTime = performance.now();
// A timer keeps the provider running when its tab is behind the dashboard.
setInterval(() => {
  const now = performance.now(); const dt = Math.min(0.1, (now - previousTime) / 1000); previousTime = now;
  if (!socket.connected || now - lastCommand > 750) brake();
  speed = Math.max(0, Math.min(100, speed + (control.throttle * 18 - control.brake * 45 - speed * 0.04) * dt));
  heading = (heading + control.steer * speed * dt * 0.4 + 360) % 360;
  offset = Math.max(-1.8, Math.min(1.8, offset + control.steer * speed * dt * 0.012));
  distance += speed / 3.6 * dt; frameId++; draw();
  document.querySelector('#speed').textContent = `${speed.toFixed(1)} km/h`;
  document.querySelector('#control').textContent = `Throttle ${control.throttle.toFixed(1)} · Brake ${control.brake.toFixed(1)} · Steer ${control.steer.toFixed(1)}`;
}, 1000 / 30);
setInterval(() => {
  if (socket.connected) socket.emit('vehicle:telemetry', { speed, throttle: control.throttle, brake: control.brake,
    steer: control.steer, heading, gear: speed > 0 ? 'D' : 'N', frameId });
}, 200);
window.addEventListener('pagehide', () => { closeStream(); socket.disconnect(); });
