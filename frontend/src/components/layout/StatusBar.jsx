/**
 * StatusBar — bottom bar showing all service statuses.
 */
import React from 'react';
import useVehicleStore from '../../store/vehicleStore';
import { formatNetworkQuality } from '../../utils/formatters';

const STATUS_CONFIG = {
  connected: { label: 'ONLINE',  dotClass: 'connected' },
  offline:   { label: 'OFFLINE', dotClass: 'disconnected' },
  idle:      { label: 'IDLE',    dotClass: 'disconnected' },
  active:    { label: 'ACTIVE',  dotClass: 'connected' },
  connecting:{ label: 'CONNECTING', dotClass: 'warning' },
  error:     { label: 'ERROR',   dotClass: 'danger' },
};

function ServiceBadge({ name, status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.offline;
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded border border-ghost-border bg-ghost-surface">
      <div className={`status-dot ${cfg.dotClass}`} />
      <div>
        <div className="text-[9px] text-ghost-muted uppercase tracking-widest leading-none">{name}</div>
        <div className="text-[11px] font-mono font-semibold text-ghost-text leading-tight mt-0.5">{cfg.label}</div>
      </div>
    </div>
  );
}

export default function StatusBar() {
  const { carlaStatus, webrtcStatus, perception, streamActive, networkQuality, packetLoss, statsAvailable, researchVersion, research, comparison } = useVehicleStore();
  const aiActive = streamActive && perception?.enabled && perception?.fresh;
  const predictionActive = streamActive && (researchVersion ? comparison?.status === 'ready' && comparison?.predictionReady : aiActive && perception?.prediction?.ready);
  const netInfo = formatNetworkQuality(networkQuality);

  const bars = [
    4, 3, 2, 1
  ].map((strength) => {
    const filled = networkQuality === 'excellent' ? 4 :
                   networkQuality === 'good'      ? 3 :
                   networkQuality === 'poor'      ? 2 : 1;
    return { strength, active: strength <= filled };
  }).reverse();

  return (
    <footer className="flex items-center justify-between px-6 py-2 border-t border-ghost-border bg-ghost-surface">
      {/* Service statuses */}
      <div className="flex items-center gap-2">
        <ServiceBadge name="CARLA"    status={carlaStatus} />
        <ServiceBadge name="WebRTC"   status={webrtcStatus} />
        <ServiceBadge name="YOLO"     status={aiActive ? 'active' : 'idle'} />
        <ServiceBadge name="Motion" status={aiActive && perception?.flow ? 'active' : 'idle'} />
        <ServiceBadge name="Prediction" status={predictionActive ? 'active' : 'idle'} />
      </div>

      {/* Center label */}
      <div className="text-[10px] font-mono text-ghost-muted tracking-widest uppercase">
        {researchVersion ? `${comparison?.view || 'Waiting for video'} · ${(research?.mode || 'STOPPED').replaceAll('_', ' ')}`
          : aiActive ? 'Live YOLO detections · Manual driving' : 'Live camera · Manual driving'}
      </div>

      {/* Network quality */}
      <div className="flex items-center gap-3">
        <div className="text-[9px] text-ghost-muted uppercase tracking-widest">Signal</div>
        <div className="flex items-end gap-0.5 h-4">
          {bars.map(({ strength, active }) => (
            <div
              key={strength}
              className={`w-1.5 rounded-sm transition-all ${active ? netInfo.barColor : 'bg-ghost-border'}`}
              style={{ height: `${(5 - strength) * 25}%` }}
            />
          ))}
        </div>
        <span className={`text-xs font-mono font-bold ${netInfo.colorClass}`}>
          {netInfo.label}
        </span>
        <span className="text-xs font-mono text-ghost-muted">
          {statsAvailable ? `${packetLoss.toFixed(1)}% video loss` : 'Video stats unavailable'}
        </span>
      </div>
    </footer>
  );
}
