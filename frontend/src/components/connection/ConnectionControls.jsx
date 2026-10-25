/**
 * ConnectionControls — Connect/disconnect vehicle and start/stop stream.
 * Now includes:
 *   - Vehicle discovery badge (shows when vehicle-sim.html is open)
 *   - Link to open the vehicle simulator
 *   - Start stream passes vehicleId to useWebRTC
 */
import React from 'react';
import { socket } from '../../services/socket';
import useVehicleStore from '../../store/vehicleStore';
import useConnection from '../../hooks/useConnection';

// ── Icons ─────────────────────────────────────────────────────────────────────
const IconConnect    = () => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>;
const IconDisconnect = () => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>;
const IconPlay       = () => <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>;
const IconStop       = () => <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>;
const IconEmergency  = () => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>;
const IconCamera     = () => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/><circle cx="12" cy="13" r="4"/></svg>;
const IconLink       = () => <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></svg>;

export default function ConnectionControls() {
  const { socketConnected, vehicleConnected, availableVehicle, connectedVehicleId, connectVehicle, disconnectVehicle } = useConnection();
  const { streamActive, setStreamActive, setWebRTCStatus } = useVehicleStore();

  // We expose startStream via a ref from VideoFeed — handled in App.jsx
  // Instead, emit stream:request directly here
  const handleStartStream = () => {
    if (!connectedVehicleId) return;
    if (availableVehicle?.name === 'CARLA-Gateway') {
      setStreamActive(true);
      return;
    }
    setWebRTCStatus('connecting');
    socket.emit('stream:request', { vehicleId: connectedVehicleId });
  };

  const handleStopStream = () => {
    if (connectedVehicleId && availableVehicle?.name !== 'CARLA-Gateway') {
      socket.emit('stream:stop', { targetId: connectedVehicleId });
    }
    setStreamActive(false);
    setWebRTCStatus('idle');
  };

  const handleEmergencyStop = () => {
    socket.emit('control:key', { key: ' ', type: 'keydown' });
    setTimeout(() => socket.emit('control:key', { key: ' ', type: 'keyup' }), 200);
  };

  const openVehicleSim = () => {
    window.open('/vehicle-sim.html', '_blank', 'width=640,height=520');
  };

  return (
    <div className="ghost-panel p-3 flex flex-col gap-3">
      <span className="text-[10px] font-mono text-ghost-muted uppercase tracking-widest">Connection</span>

      {/* Socket status */}
      <div className="flex items-center gap-2 text-[11px] font-mono px-2 py-1.5 rounded bg-ghost-surface border border-ghost-border">
        <div className={`status-dot ${socketConnected ? 'connected' : 'disconnected'}`} />
        <span className="text-ghost-muted">Server:</span>
        <span className={socketConnected ? 'text-ghost-success' : 'text-ghost-danger'}>
          {socketConnected ? 'localhost:4000' : 'Disconnected'}
        </span>
      </div>

      {/* ── Vehicle Simulator Launcher ─────────────────────────────────────── */}
      <div className="flex flex-col gap-1.5 p-2 rounded border border-dashed border-ghost-border bg-ghost-surface/40">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-mono text-ghost-muted uppercase tracking-widest flex items-center gap-1.5">
            <IconCamera />
            Vehicle Simulator
          </span>
          <button
            className="btn-ghost py-1 px-2 text-[10px] gap-1"
            onClick={openVehicleSim}
            title="Open vehicle webcam simulator in a new tab"
          >
            <IconLink />
            Open Tab
          </button>
        </div>

        {/* Vehicle discovery status */}
        {availableVehicle ? (
          <div className="flex items-center gap-2 text-[11px] font-mono animate-fade-in-up">
            <div className="status-dot connected" />
            <span className="text-ghost-success">{availableVehicle.name}</span>
            <span className="text-ghost-muted ml-auto text-[9px]">READY</span>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-[11px] font-mono text-ghost-muted">
            <div className="status-dot disconnected" />
            <span>No simulator detected</span>
          </div>
        )}
      </div>

      {/* Vehicle Connect / Disconnect */}
      <div className="flex gap-2">
        <button
          className={`btn-ghost flex-1 text-[12px] ${availableVehicle && !vehicleConnected ? 'btn-accent' : ''}`}
          onClick={connectVehicle}
          disabled={(!availableVehicle && !socketConnected) || vehicleConnected}
          title={availableVehicle ? `Connect to ${availableVehicle.name}` : 'No vehicle simulator open'}
        >
          <IconConnect />
          Connect
        </button>
        <button
          className="btn-ghost btn-danger flex-1 text-[12px]"
          onClick={disconnectVehicle}
          disabled={!vehicleConnected}
          title="Disconnect Vehicle"
        >
          <IconDisconnect />
          Disconnect
        </button>
      </div>

      {/* Stream Start / Stop */}
      <div className="flex gap-2">
        <button
          className={`btn-ghost flex-1 text-[12px] ${vehicleConnected && !streamActive ? 'btn-success' : ''}`}
          onClick={handleStartStream}
          disabled={!vehicleConnected || streamActive || !connectedVehicleId}
          title="Request webcam stream from vehicle simulator"
        >
          <IconPlay />
          Start Stream
        </button>
        <button
          className="btn-ghost flex-1 text-[12px]"
          onClick={handleStopStream}
          disabled={!streamActive}
          title="Stop Stream"
        >
          <IconStop />
          Stop
        </button>
      </div>

      {/* Helpful hint when vehicle is connected but stream hasn't started */}
      {vehicleConnected && !streamActive && (
        <p className="text-[10px] text-ghost-muted font-mono text-center animate-fade-in-up">
          ↑ Click Start Stream to begin WebRTC feed
        </p>
      )}

      {/* Emergency Stop */}
      <button
        className="btn-ghost btn-danger w-full justify-center py-3 text-[13px] font-bold tracking-wider"
        onClick={handleEmergencyStop}
        disabled={!vehicleConnected}
        title="Emergency Stop (Space)"
      >
        <IconEmergency />
        ⚡ EMERGENCY STOP
      </button>
    </div>
  );
}
