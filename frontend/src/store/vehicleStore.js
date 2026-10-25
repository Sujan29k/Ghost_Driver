/**
 * Vehicle Store (Zustand)
 * Central state for all vehicle telemetry, connection, and stream status.
 */
import { create } from 'zustand';

const useVehicleStore = create((set, get) => ({
  // ── Connection ──────────────────────────────────────────────
  socketConnected: false,
  vehicleConnected: false,
  streamActive: false,
  sessionId: null,

  // ── WebRTC Vehicle Discovery ─────────────────────────────────
  // The vehicle-sim page that is available to stream
  availableVehicle: null,   // { id: socketId, name: string } | null
  connectedVehicleId: null, // socketId of the vehicle we are connected to

  // ── Telemetry ────────────────────────────────────────────────
  speed: 0,
  fps: 0,
  latency: 0,
  packetLoss: 0,
  networkQuality: 'excellent', // excellent | good | poor | critical
  heading: 0,
  throttle: 0,
  brake: 0,
  steer: 0,
  gear: 'P',

  // ── Service Statuses ─────────────────────────────────────────
  carlaStatus: 'offline',   // offline | connected | error
  webrtcStatus: 'idle',     // idle | connecting | active | error
  yoloStatus: 'offline',
  yoloDetections: [],
  aiStatus: 'offline',
  predictionHorizonMs: 250,
  injectedLatencyMs: 500,
  cameraDelayMs: 250,
  controlDelayMs: 250,
  predictionMethod: 'RAFT-Small',
  predictionMetrics: null,
  inferenceMs: 0,
  predictionHorizonMs: 500,

  // ── Active Keys ──────────────────────────────────────────────
  activeKeys: new Set(),

  // ── Actions ──────────────────────────────────────────────────
  setSocketConnected: (v) => set({ socketConnected: v }),
  setVehicleConnected: (v) =>
    set({ vehicleConnected: v, carlaStatus: v ? 'connected' : 'offline' }),
  setStreamActive: (v) =>
    set({ streamActive: v, webrtcStatus: v ? 'active' : 'idle' }),
  setSessionId: (id) => set({ sessionId: id }),

  // Vehicle discovery (from signaling server)
  setAvailableVehicle: (v) => set({ availableVehicle: v }),
  setConnectedVehicleId: (id) => set({ connectedVehicleId: id, vehicleConnected: !!id, carlaStatus: id ? 'connected' : 'offline' }),

  updateTelemetry: (data) =>
    set({
      speed: data.speed ?? get().speed,
      fps: data.fps ?? get().fps,
      latency: data.latency ?? get().latency,
      packetLoss: data.packetLoss ?? get().packetLoss,
      networkQuality: data.networkQuality ?? get().networkQuality,
      heading: data.heading ?? get().heading,
      throttle: data.throttle ?? get().throttle,
      brake: data.brake ?? get().brake,
      steer: data.steer ?? get().steer,
      gear: data.gear ?? get().gear,
      carlaStatus: data.carlaConnected ? 'connected' : get().carlaStatus,
    }),

  addActiveKey: (key) =>
    set((s) => ({ activeKeys: new Set([...s.activeKeys, key]) })),
  removeActiveKey: (key) =>
    set((s) => {
      const next = new Set(s.activeKeys);
      next.delete(key);
      return { activeKeys: next };
    }),
  clearActiveKeys: () => set({ activeKeys: new Set() }),

  setCarlaStatus: (v) => set({ carlaStatus: v }),
  setYoloStatus: (v) => set({ yoloStatus: v }),
  setInjectedLatencyMs: (v) => set({ injectedLatencyMs: v }),
  updatePerception: (data) =>
    set({
      yoloStatus: data.modelLoaded ? 'connected' : 'offline',
      yoloDetections: data.detections ?? [],
      aiStatus: data.predictionReady ? 'connected' : 'offline',
      predictionHorizonMs: data.predictionHorizonMs ?? get().predictionHorizonMs,
      injectedLatencyMs: data.latencyMs ?? get().injectedLatencyMs,
      cameraDelayMs: data.cameraDelayMs ?? get().cameraDelayMs,
      controlDelayMs: data.controlDelayMs ?? get().controlDelayMs,
      predictionMethod: data.predictionMethod ?? get().predictionMethod,
      predictionMetrics: data.predictionMetrics ?? get().predictionMetrics,
      inferenceMs: data.inferenceMs ?? get().inferenceMs,
    }),
  setWebRTCStatus: (v) => set({ webrtcStatus: v }),
}));

export default useVehicleStore;
