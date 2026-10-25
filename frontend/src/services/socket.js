import { io } from 'socket.io-client';
export const socket = io(import.meta.env.VITE_BACKEND_URL || undefined, {
  autoConnect: false, reconnectionDelay: 1000,
});
export function request(event, data = {}) {
  return new Promise((resolve, reject) => {
    if (!socket.connected) return reject(new Error('Server is disconnected'));
    socket.timeout(5000).emit(event, data, (error, result) => {
      if (error) reject(new Error('Server did not respond'));
      else if (!result?.success) reject(new Error(result?.message || 'Request failed'));
      else resolve(result);
    });
  });
}
export default socket;
