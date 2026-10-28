import useVehicleStore from '../store/vehicleStore';
import { io } from 'socket.io-client';
export const socket = io(import.meta.env.VITE_BACKEND_URL || undefined, {
  autoConnect: false, reconnectionDelay: 1000,
});
export function request(event, data = {}) {
  return new Promise((resolve, reject) => {
    if (!socket.connected) return reject(new Error('Server is disconnected'));
    socket.timeout(10000).emit(event, data, (error, result) => {
      if (error) reject(new Error('Server did not respond'));
      else if (!result?.success) reject(new Error(result?.message || 'Request failed'));
      else resolve(result);
    });
  });
}
export default socket;

export async function researchCommand(action, data) {
  const state = useVehicleStore.getState();
  state.clearActiveKeys();
  state.patch({ researchPending: true, error: '' });
  try {
    const result = await request('research:command', { action, data });
    useVehicleStore.getState().patch({ research: result.state, emergency: result.state.stopped });
    return result;
  } catch (error) {
    useVehicleStore.getState().patch({ error: error.message });
    throw error;
  } finally {
    useVehicleStore.getState().patch({ researchPending: false });
  }
}
