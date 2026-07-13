/**
 * Header — top bar with branding and socket connection status.
 */
import React from 'react';
import useVehicleStore from '../../store/vehicleStore';

export default function Header() {
  const { socketConnected, vehicleConnected, latency } = useVehicleStore();

  return (
    <header className="flex items-center justify-between px-6 py-3 border-b border-ghost-border bg-ghost-surface relative z-50">
      {/* Logo / Brand */}
      <div className="flex items-center gap-3">
        <div className="relative w-8 h-8">
          <div className="absolute inset-0 rounded-full bg-ghost-accent opacity-20 animate-ping" />
          <div className="relative w-8 h-8 rounded-full bg-gradient-to-br from-ghost-accent to-ghost-accentDim flex items-center justify-center">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-white">
              <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2" />
              <line x1="12" y1="2" x2="12" y2="22" />
              <line x1="2" y1="8.5" x2="22" y2="8.5" />
              <line x1="2" y1="15.5" x2="22" y2="15.5" />
            </svg>
          </div>
        </div>
        <div>
          <h1 className="text-lg font-bold tracking-widest text-white uppercase leading-none">
            Ghost<span className="text-ghost-accent">Driver</span>
          </h1>
          <p className="text-[10px] text-ghost-muted tracking-widest uppercase">Teleoperation Platform</p>
        </div>
      </div>

      {/* Center — Mission Status */}
      <div className="absolute left-1/2 -translate-x-1/2 flex items-center gap-2">
        <div className={`status-dot ${vehicleConnected ? 'connected' : 'disconnected'}`} />
        <span className="text-xs font-mono tracking-widest uppercase text-ghost-muted">
          {vehicleConnected ? 'VEHICLE ONLINE' : 'NO VEHICLE'}
        </span>
      </div>

      {/* Right — Connection Info */}
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2 text-xs font-mono text-ghost-muted">
          <span className="uppercase tracking-wider">Latency</span>
          <span className={`font-bold ${latency < 100 ? 'text-ghost-success' : 'text-ghost-warning'}`}>
            {Math.round(latency)}ms
          </span>
        </div>

        <div className="flex items-center gap-2 text-xs">
          <div className={`status-dot ${socketConnected ? 'connected' : 'disconnected'}`} />
          <span className="font-mono tracking-wider text-ghost-muted uppercase">
            {socketConnected ? 'Socket Connected' : 'Disconnected'}
          </span>
        </div>

        {/* System time */}
        <ClockDisplay />
      </div>
    </header>
  );
}

function ClockDisplay() {
  const [time, setTime] = React.useState(new Date());
  React.useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="font-mono text-xs text-ghost-muted tracking-wider">
      {time.toLocaleTimeString('en-US', { hour12: false })}
    </div>
  );
}
