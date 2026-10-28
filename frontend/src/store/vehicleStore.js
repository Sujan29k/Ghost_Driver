import { create } from 'zustand';
const vehicleDefaults = { vehicleConnected: false, connectedVehicleId: null, mode: null,
  speed: 0, throttle: 0, brake: 0, steer: 0, gear: 'N', heading: 0,
  perception: null, traffic: null, research: null, researchVersion: 0, researchPending: false, comparison: null,
  videoWanted: false, streamActive: false, sessionId: null, webrtcStatus: 'idle', carlaStatus: 'offline',
  emergency: true, activeKeys: new Set(), fps: 0, packetLoss: 0, videoRtt: null, telemetryAt: null };
const useVehicleStore = create((set) => ({
  ...vehicleDefaults, socketConnected: false, vehicles: [], error: '', latency: null,
  networkQuality: 'unknown', statsAvailable: false, videoRoute: 'Unknown', relayOnly: false, retryCount: 0, turnConfigured: false, allowDemo: false,
  patch: (data) => set(data),
  resetVehicle: () => set({ ...vehicleDefaults, activeKeys: new Set(), statsAvailable: false, videoRoute: 'Unknown', retryCount: 0 }),
  updateTelemetry: (data) => set({ speed: data.speed, throttle: data.throttle, brake: data.brake,
    steer: data.steer, gear: data.gear, heading: data.heading, emergency: data.emergency,
    research: data.research || null, comparison: data.comparison || null,
    perception: data.perception || null, traffic: data.traffic || null, telemetryAt: Date.now() }),
  clearActiveKeys: () => set({ activeKeys: new Set() }),
}));
export default useVehicleStore;
