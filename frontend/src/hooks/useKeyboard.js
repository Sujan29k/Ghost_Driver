/**
 * useKeyboard — captures W/A/S/D/Space for vehicle control
 * and sends them via Socket.IO.
 */
import { useEffect, useCallback } from 'react';
import { socket } from '../services/socket';
import useVehicleStore from '../store/vehicleStore';

const CONTROL_KEYS = new Set(['w', 'a', 's', 'd', ' ']);

export function useKeyboard() {
  const { addActiveKey, removeActiveKey, vehicleConnected } = useVehicleStore();

  const handleKeyDown = useCallback(
    (e) => {
      const key = e.key.toLowerCase() === ' ' ? ' ' : e.key.toLowerCase();
      if (!CONTROL_KEYS.has(key)) return;
      e.preventDefault();

      addActiveKey(key);
      if (vehicleConnected) {
        socket.emit('control:key', { key, type: 'keydown' });
      }
    },
    [vehicleConnected, addActiveKey]
  );

  const handleKeyUp = useCallback(
    (e) => {
      const key = e.key.toLowerCase() === ' ' ? ' ' : e.key.toLowerCase();
      if (!CONTROL_KEYS.has(key)) return;
      e.preventDefault();

      removeActiveKey(key);
      if (vehicleConnected) {
        socket.emit('control:key', { key, type: 'keyup' });
      }
    },
    [vehicleConnected, removeActiveKey]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);

    // Prevent stuck keys on window blur
    const handleBlur = () => {
      useVehicleStore.getState().clearActiveKeys();
    };
    window.addEventListener('blur', handleBlur);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
      window.removeEventListener('blur', handleBlur);
    };
  }, [handleKeyDown, handleKeyUp]);
}

export default useKeyboard;
