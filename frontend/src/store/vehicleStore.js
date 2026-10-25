import { create } from 'zustand';
const vehicleDefaults = { vehicleConnected: false, connectedVehicleId: null, mode: null,
  speed: 0, throttle: 0, brake: 0, steer: 0, gear: 'N', heading: 0,
  videoWanted: false, streamActive: false, sessionId: null, webrtcStatus: 'idle', carlaStatus: 'offline',
  emergency: true, activeKeys: new Set(), fps: 0, packetLoss: 0, telemetryAt: null };
const useVehicleStore = create((set) => ({
  ...vehicleDefaults, socketConnected: false, vehicles: [], error: '', latency: null,
  networkQuality: 'unknown', yoloStatus: 'offline', aiStatus: 'offline', statsAvailable: false, videoRoute: 'Unknown', relayOnly: false, retryCount: 0, turnConfigured: false, allowDemo: false,
  patch: (data) => set(data),
  resetVehicle: () => set({ ...vehicleDefaults, activeKeys: new Set(), statsAvailable: false }),
  updateTelemetry: (data) => set({ speed: data.speed, throttle: data.throttle, brake: data.brake,
    steer: data.steer, gear: data.gear, heading: data.heading, emergency: data.emergency,
    telemetryAt: Date.now() }),
  clearActiveKeys: () => set({ activeKeys: new Set() }),
}));
export default useVehicleStore;
