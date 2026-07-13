/**
 * Socket.IO client singleton.
 * Import `socket` anywhere to send/receive events.
 */
import { io } from 'socket.io-client';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:4000';

export const socket = io(BACKEND_URL, {
  autoConnect: false,
  transports: ['websocket', 'polling'],
  reconnectionAttempts: 10,
  reconnectionDelay: 1000,
});

// Debug logging in dev
if (import.meta.env.DEV) {
  socket.onAny((event, ...args) => {
    console.debug(`[Socket ←] ${event}`, args);
  });
  socket.onAnyOutgoing((event, ...args) => {
    console.debug(`[Socket →] ${event}`, args);
  });
}

export default socket;
