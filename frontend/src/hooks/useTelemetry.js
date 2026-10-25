/**
 * useTelemetry — subscribes to telemetry:update socket events
 * and measures round-trip latency via ping/pong.
 */
import { useEffect } from 'react';
import { socket } from '../services/socket';
import useVehicleStore from '../store/vehicleStore';

const PING_INTERVAL_MS = 2000;

export function useTelemetry() {
  const updateTelemetry = useVehicleStore((s) => s.updateTelemetry);
  const updatePerception = useVehicleStore((s) => s.updatePerception);

  useEffect(() => {
    // Subscribe to live telemetry
    socket.on('telemetry:update', (data) => {
      updateTelemetry(data);
    });

    // Ping every 2 seconds to measure latency
    const pingTimer = setInterval(() => {
      if (socket.connected) {
        socket.emit('ping:measure', Date.now());
      }
    }, PING_INTERVAL_MS);

    socket.on('pong:measure', ({ latency }) => {
      updateTelemetry({ latency });
    });

    socket.on('perception:update', updatePerception);

    socket.on('latency:configure', ({ latencyMs }) => {
      useVehicleStore.getState().setInjectedLatencyMs(latencyMs);
    });

    return () => {
      socket.off('telemetry:update');
      socket.off('pong:measure');
      socket.off('perception:update');
      socket.off('latency:configure');
      clearInterval(pingTimer);
    };
  }, []);
}

export default useTelemetry;
