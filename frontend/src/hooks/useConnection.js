/**
 * useConnection — manages socket lifecycle and vehicle connect/disconnect.
 * Also listens for vehicle:available / vehicle:unavailable from signaling.
 */
import { useEffect, useCallback } from 'react';
import { socket } from '../services/socket';
import useVehicleStore from '../store/vehicleStore';

export function useConnection() {
  const {
    setSocketConnected,
    setVehicleConnected,
    setAvailableVehicle,
    setConnectedVehicleId,
    socketConnected,
    vehicleConnected,
    availableVehicle,
    connectedVehicleId,
  } = useVehicleStore();

  useEffect(() => {
    // Connect socket on mount
    socket.connect();

    socket.on('connect', () => {
      setSocketConnected(true);
      socket.emit('telemetry:request');
    });

    socket.on('disconnect', () => {
      setSocketConnected(false);
      setVehicleConnected(false);
      setAvailableVehicle(null);
      setConnectedVehicleId(null);
    });

    // ── Vehicle Discovery (from vehicle-sim.html tab) ─────────────────────
    socket.on('vehicle:available', (vehicle) => {
      setAvailableVehicle(vehicle);
      console.log('[Connection] Vehicle available:', vehicle.name, vehicle.id?.slice(0, 6));
    });

    socket.on('vehicle:unavailable', ({ id }) => {
      // If the vehicle that went offline was our connected one, disconnect
      useVehicleStore.getState().setAvailableVehicle(null);
      if (useVehicleStore.getState().connectedVehicleId === id) {
        setConnectedVehicleId(null);
      }
      console.log('[Connection] Vehicle unavailable:', id?.slice(0, 6));
    });

    // ── Legacy CARLA simulation connect/disconnect ─────────────────────────
    socket.on('vehicle:status', ({ connected }) => {
      setVehicleConnected(connected);
    });

    socket.on('vehicle:connect:ack', (result) => {
      if (result.success) setVehicleConnected(true);
    });

    socket.on('vehicle:disconnect:ack', () => {
      setVehicleConnected(false);
    });

    return () => {
      socket.off('connect');
      socket.off('disconnect');
      socket.off('vehicle:available');
      socket.off('vehicle:unavailable');
      socket.off('vehicle:status');
      socket.off('vehicle:connect:ack');
      socket.off('vehicle:disconnect:ack');
      socket.disconnect();
    };
  }, []);

  /** Connect to an available vehicle (WebRTC path) */
  const connectVehicle = useCallback(() => {
    const { availableVehicle } = useVehicleStore.getState();
    if (availableVehicle) {
      setConnectedVehicleId(availableVehicle.id);
    } else {
      // Legacy CARLA simulation fallback
      socket.emit('vehicle:connect');
    }
  }, []);

  /** Disconnect from vehicle */
  const disconnectVehicle = useCallback(() => {
    setConnectedVehicleId(null);
    socket.emit('vehicle:disconnect');
  }, []);

  return {
    socketConnected,
    vehicleConnected,
    availableVehicle,
    connectedVehicleId,
    connectVehicle,
    disconnectVehicle,
  };
}

export default useConnection;
