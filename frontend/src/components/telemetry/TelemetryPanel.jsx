/**
 * TelemetryPanel — side panel showing all live vehicle metrics.
 */
import React from 'react';
import TelemetryCard from './TelemetryCard';
import useVehicleStore from '../../store/vehicleStore';
import { formatLatency, formatFPS, formatNetworkQuality } from '../../utils/formatters';

function MeterBar({ value, max = 100, colorClass = 'bg-ghost-accent' }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div className="meter-bar mt-1.5">
      <div className={`meter-fill ${colorClass}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function SpeedGauge({ speed, max = 120 }) {
  const pct = Math.min(100, (speed / max) * 100);
  const angle = -135 + (pct / 100) * 270;
  const color = speed < 40 ? '#00ff87' : speed < 80 ? '#ffaa00' : '#ff3b5c';

  return (
    <div className="ghost-panel p-4 flex flex-col items-center gap-2">
      <span className="text-[10px] font-mono text-ghost-muted uppercase tracking-widest">Speedometer</span>
      <div className="relative w-28 h-28">
        {/* Background arc */}
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-180">
          <circle cx="50" cy="50" r="40" fill="none" stroke="#1a3a5c" strokeWidth="6" strokeDasharray="188 251" strokeLinecap="round" />
          <circle
            cx="50" cy="50" r="40" fill="none" stroke={color}
            strokeWidth="6"
            strokeDasharray={`${(pct / 100) * 188} 251`}
            strokeLinecap="round"
            style={{ transition: 'stroke-dasharray 0.3s, stroke 0.3s', filter: `drop-shadow(0 0 6px ${color})` }}
          />
        </svg>
        {/* Center readout */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-black font-mono leading-none" style={{ color }}>{Math.round(speed)}</span>
          <span className="text-[9px] font-mono text-ghost-muted">km/h</span>
        </div>
      </div>
    </div>
  );
}

function ControlInputBar({ label, value, colorClass, invert = false }) {
  const pct = Math.abs(value) * 100;
  const side = invert && value < 0;
  return (
    <div className="flex items-center gap-2 text-[11px] font-mono">
      <span className="text-ghost-muted w-14 uppercase tracking-wider">{label}</span>
      <div className="flex-1 bg-ghost-surface rounded-sm h-2 overflow-hidden">
        {!invert ? (
          <div className={`h-full ${colorClass} transition-all`} style={{ width: `${pct}%` }} />
        ) : (
          <div className="relative h-full">
            <div className="absolute inset-x-0 inset-y-0 flex items-center justify-center">
              <div className="w-px h-full bg-ghost-border" />
            </div>
            <div
              className={`h-full ${colorClass} transition-all absolute top-0`}
              style={{ width: `${pct / 2}%`, [side ? 'right' : 'left']: '50%' }}
            />
          </div>
        )}
      </div>
      <span className="text-ghost-text w-10 text-right">{(value * 100).toFixed(0)}%</span>
    </div>
  );
}

export default function TelemetryPanel() {
  const { speed, fps, latency, packetLoss, videoRtt, videoRoute, networkQuality, throttle, brake, steer, gear, heading, statsAvailable, perception, traffic, streamActive } = useVehicleStore();
  const aiActive = streamActive && perception?.enabled && perception?.fresh;

  const latInfo = formatLatency(latency);
  const fpsInfo = formatFPS(fps);
  const netInfo = formatNetworkQuality(networkQuality);

  return (
    <div className="flex flex-col gap-3 w-64 h-full overflow-y-auto pr-0.5" style={{ scrollbarWidth: 'thin' }}>
      {/* Speed Gauge */}
      <SpeedGauge speed={speed} />

      <div className="ghost-panel p-3 text-xs flex flex-col gap-2" aria-label="Scene and perception">
        <span className="font-mono text-ghost-accent">Scene and perception</span>
        <span>Spawned cars: {traffic?.vehicles ?? '—'} · Bikes: {traffic?.bicycles ?? '—'}</span>
        <span>Pedestrians: {traffic?.pedestrians ?? '—'}</span>
        <span>YOLO: {aiActive ? 'Processing live frames' : 'Inactive'}</span>
        <span>Road objects in frame: {aiActive ? perception.objects : '—'}</span>
        <span>Processing: {aiActive && perception.inferenceMs != null ? `${Math.round(perception.inferenceMs)} ms` : '—'}</span>
        <span>Prediction: {aiActive && perception.prediction?.method !== 'off' && perception.prediction?.method
          ? `${perception.prediction.method.toUpperCase()} · ${perception.prediction.ready ? `+${perception.prediction.horizonMs} ms estimate` : 'Buffering'}` : 'Off'}</span>
        {aiActive && perception.warning && <span className="text-ghost-warning">Large object in view. Advisory only; use the driving controls to brake.</span>}
        <span className="text-ghost-muted">Spawned actors may be outside the camera view.</span>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-2 gap-2">
        <TelemetryCard label="Video RTT" value={videoRtt == null ? '—' : `${videoRtt} ms`}
          colorClass="text-ghost-accent" subtext="Browser ↔ sender" />
        <TelemetryCard label="Video route" value={videoRoute} colorClass="text-ghost-text" valueClassName="text-base"
          subtext="Selected WebRTC path" />
        <TelemetryCard
          label="FPS"
          value={statsAvailable ? fpsInfo.label : '—'}
          colorClass={fpsInfo.colorClass}
          subtext="Received frames"
          icon={
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M4 6h16v2H4zm0 5h16v2H4zm0 5h16v2H4z"/></svg>
          }
        />
        <TelemetryCard
          label="Server RTT"
          value={latInfo.label}
          colorClass={latInfo.colorClass}
          subtext="Browser ↔ backend"
          icon={
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
          }
        />
        <TelemetryCard
          label="Packet Loss"
          value={statsAvailable ? packetLoss.toFixed(1) : '—'}
          unit="%"
          colorClass={packetLoss < 1 ? 'text-ghost-success' : 'text-ghost-warning'}
          subtext="Latest interval"
        />
        <TelemetryCard
          label="Network"
          value={netInfo.label}
          colorClass={netInfo.colorClass}
          subtext="Local backend RTT"
        />
      </div>

      {/* Vehicle Controls Readout */}
      <div className="ghost-panel p-3 flex flex-col gap-3">
        <span className="text-[10px] font-mono text-ghost-muted uppercase tracking-widest">Control Inputs</span>
        <ControlInputBar label="Throttle" value={throttle} colorClass="bg-ghost-success" />
        <ControlInputBar label="Brake"    value={brake}    colorClass="bg-ghost-danger" />
        <ControlInputBar label="Steer"    value={steer}    colorClass="bg-ghost-accent" invert />
      </div>

      {/* Nav Info */}
      <div className="grid grid-cols-2 gap-2">
        <TelemetryCard
          label="Gear"
          value={gear}
          colorClass="text-ghost-accent"
          subtext="Current"
        />
        <TelemetryCard
          label="Heading"
          value={`${Math.round(heading)}°`}
          colorClass="text-ghost-text"
          subtext="Direction"
        />
      </div>
    </div>
  );
}
