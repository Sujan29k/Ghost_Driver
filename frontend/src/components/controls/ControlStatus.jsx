/**
 * ControlStatus — shows current active keyboard keys with visual feedback.
 */
import React from 'react';
import useVehicleStore from '../../store/vehicleStore';

export default function ControlStatus() {
  const { activeKeys, streamActive, emergency } = useVehicleStore();

  const keys = [
    { key: 'w', label: 'W', action: 'THROTTLE', top: 0, left: 1 },
    { key: 'a', label: 'A', action: 'LEFT',     top: 1, left: 0 },
    { key: 's', label: 'S', action: 'BRAKE',    top: 1, left: 1 },
    { key: 'd', label: 'D', action: 'RIGHT',    top: 1, left: 2 },
  ];

  const vehicleConnected = streamActive && !emergency;
  const spaceActive = activeKeys.has(' ');

  return (
    <div className="ghost-panel p-3 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-mono text-ghost-muted uppercase tracking-widest">Controls</span>
        <div className="flex items-center gap-1.5">
          <div className={`status-dot ${vehicleConnected ? 'connected' : 'disconnected'}`} />
          <span className="text-[10px] font-mono text-ghost-muted">
            {vehicleConnected ? 'ACTIVE' : 'INACTIVE'}
          </span>
        </div>
      </div>

      {/* WASD grid */}
      <div className="grid grid-cols-3 gap-1.5 w-fit mx-auto" style={{ gridTemplateRows: 'repeat(2, auto)' }}>
        {keys.map(({ key, label, action, top, left }) => {
          const isActive = activeKeys.has(key);
          return (
            <div
              key={key}
              className={`kbd ${isActive ? 'active' : ''}`}
              style={{ gridRow: top + 1, gridColumn: left + 1 }}
              title={action}
            >
              {label}
            </div>
          );
        })}
      </div>

      {/* Spacebar */}
      <div className={`kbd w-full justify-center text-[10px] ${spaceActive ? 'active' : ''}`}>
        <span className="text-ghost-danger font-bold">⚡ SPACE — EMERGENCY STOP</span>
      </div>

      {!vehicleConnected && (
        <p className="text-[10px] text-ghost-muted font-mono text-center">
          Start video and resume controls to drive
        </p>
      )}
    </div>
  );
}
