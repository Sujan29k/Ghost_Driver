/**
 * TelemetryCard — reusable metric display card.
 */
import React from 'react';

export default function TelemetryCard({ label, value, unit, colorClass = 'text-ghost-accent', valueClassName = 'text-2xl', icon, subtext }) {
  return (
    <div className="ghost-panel ghost-panel-hover p-3 flex flex-col gap-1 animate-fade-in-up">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-mono text-ghost-muted uppercase tracking-widest">{label}</span>
        {icon && <span className="text-ghost-muted opacity-60">{icon}</span>}
      </div>
      <div className="flex items-end gap-1.5">
        <span className={`value-display ${valueClassName} font-black leading-none ${colorClass}`}>
          {value}
        </span>
        {unit && (
          <span className="text-xs text-ghost-muted font-mono mb-0.5">{unit}</span>
        )}
      </div>
      {subtext && (
        <div className="text-[10px] text-ghost-muted font-mono">{subtext}</div>
      )}
    </div>
  );
}
