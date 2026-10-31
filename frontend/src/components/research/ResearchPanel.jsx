import React, { useEffect, useRef, useState } from 'react';
import useVehicleStore from '../../store/vehicleStore';
import { researchCommand, socket } from '../../services/socket';

const field = 'w-full rounded bg-ghost-bg border border-ghost-border p-1 text-ghost-text';
const button = 'rounded border border-ghost-border p-2 hover:border-ghost-accent disabled:opacity-40 text-left';
export default function ResearchPanel() {
  const { researchVersion, research, researchPending, streamActive, speed, gear } = useVehicleStore();
  const [video, setVideo] = useState({ delayMs: 200, method: 'raft', view: 'compare', reference: false });
  const [scenario, setScenario] = useState({ name: 'normal', severity: 1, seed: 2026, blockage: 'partial', weather: {} });
  const [route, setRoute] = useState('straight');
  const [label, setLabel] = useState('');
  const [order, setOrder] = useState(1);
  const [frames, setFrames] = useState(false);
  const [outcome, setOutcome] = useState('completed');
  const [policy, setPolicy] = useState({ stallSeconds: 12, blockedSeconds: 2, deviationMeters: 5, deviationSeconds: 2, weatherThreshold: 80, hazardDistance: 12 });
  const notified = useRef(null);
  const videoConfig = research?.video;
  const wetScenario = ['rain', 'flood', 'combined'].includes(scenario.name);
  const scenarioDefaults = { precipitation: [35, 65, 95][scenario.severity - 1], wetness: wetScenario ? 100 : 0,
    puddles: ['flood', 'combined'].includes(scenario.name) ? 90 : wetScenario ? 60 : 0,
    fogDensity: wetScenario ? [10, 30, 60][scenario.severity - 1] : 0, sunAltitude: wetScenario ? 15 : 65,
    friction: [.8, .5, .3][scenario.severity - 1] };
  useEffect(() => {
    if (videoConfig) setVideo({ delayMs: videoConfig.delayMs, method: videoConfig.method, view: videoConfig.view, reference: videoConfig.reference });
  }, [videoConfig?.delayMs, videoConfig?.method, videoConfig?.view, videoConfig?.reference]);
  useEffect(() => {
    const trigger = research?.takeover?.triggerNs;
    if (research?.mode === 'TAKEOVER_REQUESTED' && trigger && notified.current !== trigger) {
      notified.current = trigger;
      socket.emit('research:notice', { triggerNs: trigger, browserTimestamp: Date.now() });
    }
  }, [research?.mode, research?.takeover?.triggerNs]);
  if (!researchVersion) return null;
  const send = (action, data) => {
    document.activeElement?.blur();
    return researchCommand(action, data).catch(() => {});
  };
  const busy = researchPending || !research;
  const stopped = speed <= (research?.directionLimitKmh ?? 1);
  const status = researchPending ? 'Pending sender acknowledgement…' : `Acknowledged: ${research?.mode || 'Waiting for sender'}`;
  return <section className="ghost-panel p-3 text-xs flex flex-col gap-2" aria-label="Research controls">
    <h2 className="font-mono text-ghost-accent">Research controls</h2>
    <p role="status">{status}</p>
    <p>Direction: {research?.direction || 'forward'} · Actual gear: {gear}</p>
    <label>Drive direction (R toggles)
      <select aria-label="Drive direction" className={field} value={research?.direction || 'forward'} disabled={busy}
        onChange={e => send('direction', { direction: e.target.value })}>
        <option value="forward">Forward</option><option value="reverse">Reverse</option>
      </select>
    </label>
    <p className="text-ghost-muted">Switch below {research?.directionLimitKmh ?? 1} km/h, then take manual control. W uses 50% throttle; S brakes in either direction.</p>
    <button className={button} disabled={busy || !streamActive || !stopped || research?.direction === 'reverse'} onClick={() => send('mode', { mode: 'AUTONOMOUS' })}>
      {research?.takeover ? 'Return to autonomy' : 'Start autonomous driving'}
    </button>
    <button className={button} disabled={busy || !streamActive} onClick={() => send('mode', { mode: 'MANUAL' })}>Take manual control</button>
    <button className={button} disabled={busy} onClick={() => send('mode', { mode: 'STOPPED' })}>Stop driving</button>
    <p>Start autonomous driving after video arrives. When a hazard requests takeover, the car brakes; click Take manual control, then use W/A/S/D.</p>
    {research?.reason && <p role="status">Driving status: {research.reason}</p>}
    <p>Autonomy: CARLA Traffic Manager. YOLO/RAFT are perception and image estimation models.</p>
    {research?.takeover && <p className="text-ghost-warning">{research.takeover.reason} · Source: {research.takeover.source}</p>}
    <p className="text-ghost-muted">Settings and resets stop the car. Starting a scenario or recording during autonomy keeps supervision active.</p>
    <details>
      <summary>Route and scenarios</summary>
      <div className="flex flex-col gap-2 mt-2">
        <label>Route preference<select className={field} value={route} onChange={e => setRoute(e.target.value)}>
          <option value="straight">Straight where available</option><option value="left">Prefer left turns</option><option value="right">Prefer right turns</option>
        </select></label>
        <button className={button} disabled={busy || !stopped} onClick={() => send('route', { route })}>Set route from current position</button>
        <label>Scenario<select aria-label="Scenario" className={field} value={scenario.name} onChange={e => setScenario({ ...scenario, name: e.target.value, weather: {} })}>
          <option value="normal">Normal driving</option><option value="rain">Heavy rain + low friction</option><option value="landslide">Landslide-style roadblock</option><option value="flood">Flood approximation</option><option value="combined">Rain + roadblock</option>
        </select></label>
        <label>Severity<select className={field} value={scenario.severity} onChange={e => setScenario({ ...scenario, severity: +e.target.value, weather: {} })}>
          {[1, 2, 3].map(n => <option key={n} value={n}>{n}</option>)}
        </select></label>
        <label>Obstruction<select className={field} value={scenario.blockage} onChange={e => setScenario({ ...scenario, blockage: e.target.value })}>
          <option value="partial">Partial — test manual recovery</option><option value="full">Full — stop if impassable</option>
        </select></label>
        <label>Seed<input className={field} type="number" min="0" max="2147483647" value={scenario.seed} onChange={e => setScenario({ ...scenario, seed: +e.target.value })} /></label>
        <p>Visual weather and local tire friction are configured separately. These fields apply to rain/flood/combined scenarios; they do not simulate flood depth.</p>
        {[['precipitation', 'Rain (%)', 0, 100, 1], ['wetness', 'Road wetness (%)', 0, 100, 1],
          ['puddles', 'Puddle/deposit appearance (%)', 0, 100, 1], ['fogDensity', 'Fog density (%)', 0, 100, 1],
          ['sunAltitude', 'Sun altitude (degrees)', -90, 90, 1], ['friction', 'Local friction coefficient', 0.05, 2, 0.05]].map(([key, title, min, max, step]) =>
          <label key={key}>{title}<input aria-label={title} className={field} type="number" min={min} max={max} step={step}
            value={scenario.weather[key] ?? scenarioDefaults[key]} disabled={!wetScenario} onChange={e => setScenario({ ...scenario, weather: { ...scenario.weather, [key]: +e.target.value } })} /></label>)}
        <button className={button} disabled={busy || (!stopped && research?.mode !== 'AUTONOMOUS')} onClick={() => send('scenario', { ...scenario, operation: 'start' })}>Start selected scenario</button>
        <button className={button} disabled={busy || !stopped} onClick={() => send('scenario', { ...scenario, operation: 'reset' })}>Reset selected scenario (stopped)</button>
        <button className={button} disabled={busy || !stopped} onClick={() => send('scenario', { ...scenario, name: 'none', operation: 'reset' })}>Stop scenario and restore environment</button>
        <p>Introduce a hazard while autonomy is running to test takeover. Stop driving and wait below the direction threshold before reset.</p>
        <p>Active: {research?.scenario?.name || 'none'}. Reset retains the ego and camera; removes owned hazards and restores weather.</p>
        {research?.scenario?.effects?.map(effect => <p key={effect}>{effect}</p>)}
        {research?.scenario?.active && <p>Applied rain: {research.scenario.weather?.precipitation ?? '—'}% · Fog: {research.scenario.weather?.fog_density ?? '—'}% · Local friction: {research.scenario.friction ?? 'unchanged'}</p>}
        {research?.scenario?.warnings?.map(warning => <p className="text-ghost-warning" key={warning}>{warning}</p>)}
      </div>
    </details>
    <details open>
      <summary>Video experiment</summary>
      <div className="flex flex-col gap-2 mt-2">
        <label>Injected video delay<select className={field} value={video.delayMs} onChange={e => setVideo({ ...video, delayMs: +e.target.value })}>
          {[0, 100, 200, 500, 800].map(n => <option key={n} value={n}>{n} ms</option>)}
        </select></label>
        <label>Prediction method<select className={field} value={video.method} onChange={e => setVideo({ ...video, method: e.target.value })}>
          <option value="off">Off</option><option value="raft">RAFT-Small</option><option value="farneback">Farneback</option>
        </select></label>
        <label>Display mode<select className={field} value={video.view} onChange={e => setVideo({ ...video, view: e.target.value })}>
          <option value="compare">Compare delayed / predicted</option><option value="delayed">Delayed only</option><option value="predicted">Predicted only</option><option value="reference">Vehicle reference only</option>
        </select></label>
        <label><input type="checkbox" checked={video.reference} onChange={e => setVideo({ ...video, reference: e.target.checked })} /> Include reference in Compare</label>
        <button className={button} disabled={busy} onClick={() => send('video', video)}>Apply video settings</button>
        <button className={button} disabled={busy} onClick={() => send('buffer', { operation: 'clear' })}>Clear frame buffer</button>
        <p>Prediction is a synthesized estimate. Reference also has transmission delay. Driving commands are never artificially delayed.</p>
      </div>
    </details>
    <details>
      <summary>Takeover thresholds</summary>
      {Object.entries({ stallSeconds: 'No progress (s)', blockedSeconds: 'Obstacle persistence (s)', deviationMeters: 'Route deviation (m)', deviationSeconds: 'Deviation persistence (s)', weatherThreshold: 'Scripted rain threshold (%)', hazardDistance: 'Hazard distance (m)' }).map(([key, title]) =>
        <label className="block mt-2" key={key}>{title}<input className={field} type="number" step="0.5" value={policy[key]} onChange={e => setPolicy({ ...policy, [key]: +e.target.value })} /></label>)}
      <button className={button + ' mt-2'} disabled={busy} onClick={() => send('policy', policy)}>Apply takeover policy</button>
    </details>
    <details>
      <summary>Trial recording</summary>
      <div className="flex flex-col gap-2 mt-2">
        <label>Trial label<input className={field} maxLength="80" value={label} onChange={e => setLabel(e.target.value)} /></label>
        <label>Trial order<input className={field} type="number" min="1" max="10000" value={order} onChange={e => setOrder(+e.target.value)} /></label>
        <label><input type="checkbox" checked={frames} onChange={e => setFrames(e.target.checked)} /> Save raw aligned images (max 2 sets/s)</label>
        <button className={button} disabled={busy || research?.trial?.active} onClick={() => send('trial', { operation: 'start', label, order, saveFrames: frames })}>Start recording on sender</button>
        <label>Outcome<select className={field} value={outcome} onChange={e => setOutcome(e.target.value)}><option value="completed">Completed</option><option value="aborted">Aborted</option><option value="blocked">Stopped at impassable hazard</option></select></label>
        <button className={button} disabled={busy || !research?.trial?.active} onClick={() => send('trial', { operation: 'stop', outcome })}>Stop recording</button>
        <p>Use delayed-only and predicted-only trials, hide reference, vary trial order and repeat. Compare image metrics separately from driving outcomes.</p>
      </div>
    </details>
  </section>;
}
