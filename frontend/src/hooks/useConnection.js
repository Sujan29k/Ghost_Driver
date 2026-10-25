import { useEffect } from 'react';
import { socket, request } from '../services/socket';
import { setIceServers } from '../services/rtcConfig';
import useVehicleStore from '../store/vehicleStore';
export function useConnection() {
  useEffect(() => {
    const state = useVehicleStore.getState;
    const onConnect = async () => {
      try {
        const config = await request('rtc:config');
        if (!socket.connected) return;
        setIceServers(config.iceServers);
        state().patch({ socketConnected: true, error: '', allowDemo: config.allowDemo,
          turnConfigured: config.iceServers.some((s) => /^turns?:/.test(s.urls)) });
        socket.emit('vehicles:request');
      } catch (error) { state().patch({ error: error.message }); }
    };
    const onDisconnect = () => { setIceServers([]); state().resetVehicle(); state().patch({ socketConnected: false, vehicles: [], turnConfigured: false, allowDemo: false, latency: null, networkQuality: 'unknown' }); };
    const onVehicles = (vehicles) => state().patch({ vehicles, carlaStatus: vehicles.some((v) => v.id === state().connectedVehicleId && v.ready && v.mode === 'carla') ? 'connected' : 'offline' });
    const onReleased = ({ reason }) => { state().resetVehicle(); state().patch({ error: reason === 'Operator disconnected' ? '' : reason }); };
    const onEmergency = ({ active }) => { state().clearActiveKeys(); state().patch({ emergency: active }); };
    const onError = (error) => state().patch({ error: `Backend connection: ${error.message}` });
    socket.on('connect', onConnect).on('disconnect', onDisconnect).on('vehicles:list', onVehicles)
      .on('vehicle:released', onReleased).on('vehicle:emergency', onEmergency).on('connect_error', onError);

    if (socket.connected) onConnect();
    return () => {
      socket.off('connect', onConnect).off('disconnect', onDisconnect).off('vehicles:list', onVehicles)
        .off('vehicle:released', onReleased).off('vehicle:emergency', onEmergency).off('connect_error', onError);
      socket.disconnect();
    };
  }, []);
  return {
    connectVehicle: async (vehicleId) => {
      const result = await request('vehicle:connect', { vehicleId });
      useVehicleStore.getState().patch({ vehicleConnected: true, connectedVehicleId: result.vehicle.id,
        mode: result.vehicle.mode, carlaStatus: result.vehicle.ready ? 'connected' : 'offline',
        emergency: result.emergency, error: '' });
    },
    disconnectVehicle: () => request('vehicle:disconnect'),
  };
}
export default useConnection;
