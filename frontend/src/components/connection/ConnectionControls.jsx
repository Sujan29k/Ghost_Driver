import React, { useState } from 'react';
import { socket, request } from '../../services/socket';
import useVehicleStore from '../../store/vehicleStore';
import useConnection from '../../hooks/useConnection';
import { senderStatus } from '../../utils/senderStatus';
export default function ConnectionControls() {
  const state = useVehicleStore();
  const { connectVehicle, disconnectVehicle } = useConnection();
  const [token, setToken] = useState('');
  const [pending, setPending] = useState(false);
  const run = async (action) => {
    setPending(true); state.patch({ error: '' });
    try { await action(); } catch (error) { state.patch({ error: error.message }); }
    finally { setPending(false); document.activeElement?.blur(); }
  };
  return <div className="ghost-panel p-3 flex flex-col gap-3">
    <h2 className="text-xs uppercase tracking-widest text-ghost-muted">Vehicle connection</h2>
    {!state.socketConnected && <form onSubmit={(event) => {
      event.preventDefault(); socket.auth = { role: 'dashboard', token }; socket.connect(); setToken('');
    }} className="flex flex-col gap-2">
      <label className="text-sm" htmlFor="connection-token">Dashboard token</label>
      <input id="connection-token" type="password" autoComplete="off" value={token}
        onChange={(event) => setToken(event.target.value)} className="bg-black/40 border p-2 rounded" required />
      <button className="btn-ghost btn-accent" type="submit">Connect backend</button>
      <p className="text-xs text-ghost-muted">Token stays in memory for reconnects. Re-enter after refreshing.</p>
    </form>}
    {state.socketConnected && <button className="btn-ghost" onClick={() => { socket.disconnect(); socket.auth = {}; }}>Lock dashboard</button>}
    {state.allowDemo && <button className="btn-ghost btn-accent" onClick={() => window.open('/vehicle-sim.html', '_blank')}>Open demo vehicle</button>}
    <p className="text-xs text-ghost-muted">Connect to your sender, then start video. Controls remain stopped until you resume.</p>
    {!state.vehicles.length && <><p className="text-sm text-ghost-muted">No vehicle available</p>
      {state.socketConnected && <p className="text-xs text-ghost-muted">Keep your Mac’s tunnel running. Start CARLA and the Python bridge on the GPU computer using the current tunnel URL and sender token.</p>}</>}
    {state.vehicles.map((v) => <div key={v.id} className="border border-ghost-border p-2 rounded">
      <p className="text-sm">{v.name}</p><p className="text-xs text-ghost-muted">{v.mode === 'mock' ? 'Synthetic demo' : 'CARLA camera'} · {senderStatus(v)}{v.busy ? ' · In use' : ''}</p>
      <button className="btn-ghost mt-2" disabled={pending || state.vehicleConnected || v.busy}
        onClick={() => run(() => connectVehicle(v.id))}>Connect</button>
    </div>)}
    <button className="btn-ghost" disabled={!state.vehicleConnected || pending} onClick={() => run(disconnectVehicle)}>Disconnect</button>
    <button className="btn-ghost btn-accent" disabled={!state.vehicleConnected || state.webrtcStatus === 'connecting' || state.streamActive || pending}
      onClick={() => { state.patch({ retryCount: 0, videoWanted: true }); run(() => request('stream:request', { vehicleId: state.connectedVehicleId, relayOnly: state.relayOnly })); }}>{state.webrtcStatus === 'connecting' ? 'Connecting video…' : 'Start stream'}</button>
    <label className="text-xs"><input type="checkbox" checked={state.relayOnly}
      disabled={!state.turnConfigured || state.webrtcStatus !== 'idle'}
      onChange={(e) => state.patch({ relayOnly: e.target.checked })} /> Test TURN only</label>
    <p className="text-xs text-ghost-muted">{!state.socketConnected
      ? 'Connect backend with your dashboard token to check TURN configuration.'
      : state.turnConfigured
        ? 'TURN is configured. Stop video, then use Test TURN only to verify relay access.'
        : 'TURN is not configured on the backend.'}</p>
    <button className="btn-ghost" disabled={!state.vehicleConnected} onClick={() => { state.patch({ videoWanted: false, retryCount: 0 }); socket.emit('stream:stop', {}); }}>Stop stream</button>
    <button className="btn-ghost btn-danger" disabled={!state.vehicleConnected} onClick={() => run(() => request('control:emergency'))}>Emergency stop</button>
    {state.emergency && <><p role="status" className="text-ghost-danger text-sm">{state.researchVersion
      ? `Controls stopped — ${state.research?.reason || 'Select a driving mode below'}` : 'Controls stopped — emergency stop active'}</p>
      {!state.researchVersion && <button className="btn-ghost" disabled={!state.streamActive} onClick={() => run(() => request('control:resume'))}>Resume controls</button>}</>}
    {state.error && <p role="alert" className="text-sm text-ghost-danger break-words">{state.error}</p>}
  </div>;
}
