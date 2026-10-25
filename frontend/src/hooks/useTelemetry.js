import { useEffect } from 'react';
import { socket } from '../services/socket';
import useVehicleStore from '../store/vehicleStore';
export default function useTelemetry() {
  useEffect(() => {
    const onTelemetry = (data) => {
      const state = useVehicleStore.getState();
      if (state.connectedVehicleId === data.vehicleId) state.updateTelemetry(data);
    };
    socket.on('telemetry:update', onTelemetry);
    const timer = setInterval(() => {
      if (!socket.connected) return;
      const start = performance.now();
      socket.timeout(3000).emit('ping:measure', {}, (error) => {
        const state = useVehicleStore.getState();
        if (error) return state.patch({ latency: null, networkQuality: 'unknown' });
        const latency = Math.round(performance.now() - start);
        state.patch({ latency, networkQuality: latency < 50 ? 'excellent' : latency < 100 ? 'good' : latency < 200 ? 'poor' : 'critical' });
      });
    }, 2000);
    return () => { clearInterval(timer); socket.off('telemetry:update', onTelemetry); };
  }, []);
}
