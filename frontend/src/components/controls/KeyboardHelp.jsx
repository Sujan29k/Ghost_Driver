/**
 * KeyboardHelp — quick reference card for keyboard bindings.
 */
import React from 'react';

const BINDINGS = [
  { keys: ['W'],     action: 'Throttle',       color: 'text-ghost-success' },
  { keys: ['S'],     action: 'Brake',          color: 'text-ghost-warning' },
  { keys: ['A'],     action: 'Turn Left',       color: 'text-ghost-accent' },
  { keys: ['D'],     action: 'Turn Right',      color: 'text-ghost-accent' },
  { keys: ['R'],     action: 'Toggle Forward / Reverse (stopped)' , color: 'text-ghost-warning' },
  { keys: ['SPACE'], action: 'Emergency Stop',  color: 'text-ghost-danger' },
];

export default function KeyboardHelp() {
  return (
    <div className="ghost-panel p-3 flex flex-col gap-2">
      <span className="text-[10px] font-mono text-ghost-muted uppercase tracking-widest">Keybindings</span>
      <div className="flex flex-col gap-1.5">
        {BINDINGS.map(({ keys, action, color }) => (
          <div key={action} className="flex items-center justify-between gap-2">
            <div className="flex gap-1">
              {keys.map((k) => (
                <span key={k} className="kbd text-[10px]">{k}</span>
              ))}
            </div>
            <span className={`text-[11px] font-mono ${color}`}>{action}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
