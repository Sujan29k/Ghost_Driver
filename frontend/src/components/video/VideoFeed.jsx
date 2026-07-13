/**
 * VideoFeed — main camera / stream viewport.
 * Phase 1: shows a waiting state with futuristic overlay.
 * Phase 2: video element receives WebRTC srcObject from CARLA.
 */
import React, { useRef } from 'react';
import useVehicleStore from '../../store/vehicleStore';
import useWebRTC from '../../hooks/useWebRTC';
import { formatHeading } from '../../utils/formatters';

export default function VideoFeed() {
  const videoRef = useRef(null);
  const { streamActive, vehicleConnected, speed, heading, fps, networkQuality } = useVehicleStore();
  const { startStream, stopStream } = useWebRTC(videoRef);

  return (
    <div className="ghost-panel relative flex-1 overflow-hidden scanlines">
      {/* Video element (hidden when no stream) */}
      <video
        ref={videoRef}
        autoPlay
        muted
        playsInline
        className={`absolute inset-0 w-full h-full object-cover ${streamActive ? 'opacity-100' : 'opacity-0'}`}
      />

      {/* No-stream overlay */}
      {!streamActive && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 grid-bg">
          {/* Crosshair */}
          <div className="relative w-32 h-32">
            <div className="absolute inset-0 border border-ghost-border rounded-full animate-spin-slow opacity-30" />
            <div className="absolute inset-4 border border-ghost-accent/30 rounded-full animate-[spin_5s_linear_infinite_reverse]" />
            {/* Center dot */}
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-2 h-2 rounded-full bg-ghost-accent animate-pulse" />
            </div>
            {/* Tick marks */}
            {[0, 90, 180, 270].map((deg) => (
              <div
                key={deg}
                className="absolute inset-0 flex items-center justify-center"
                style={{ transform: `rotate(${deg}deg)` }}
              >
                <div className="w-full h-px bg-ghost-border opacity-50" />
              </div>
            ))}
          </div>

          <div className="text-center">
            <p className="text-ghost-muted text-xs font-mono tracking-widest uppercase animate-pulse">
              {vehicleConnected ? 'Vehicle Connected — Ready to Stream' : 'Waiting for Vehicle Stream...'}
            </p>
            <p className="text-ghost-border text-[10px] font-mono mt-1">
              WebRTC · CARLA Camera · Phase 2
            </p>
          </div>

          {vehicleConnected && (
            <button
              className="btn-ghost btn-accent text-xs"
              onClick={startStream}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
              Start Stream
            </button>
          )}
        </div>
      )}

      {/* HUD Overlays (always visible when vehicle connected or streaming) */}
      {(vehicleConnected || streamActive) && (
        <>
          {/* Top-left: Stream status */}
          <div className="absolute top-3 left-3 flex items-center gap-2 px-2.5 py-1.5 rounded bg-black/60 backdrop-blur-sm border border-ghost-border">
            <div className={`w-2 h-2 rounded-full ${streamActive ? 'bg-ghost-success animate-pulse' : 'bg-ghost-warning animate-pulse'}`} />
            <span className="text-[11px] font-mono tracking-widest text-ghost-text">
              {streamActive ? 'LIVE' : 'STANDBY'}
            </span>
          </div>

          {/* Top-right: FPS */}
          <div className="absolute top-3 right-3 px-2.5 py-1.5 rounded bg-black/60 backdrop-blur-sm border border-ghost-border">
            <span className="text-[11px] font-mono text-ghost-muted">FPS </span>
            <span className={`text-[11px] font-mono font-bold ${fps >= 30 ? 'text-ghost-success' : fps >= 15 ? 'text-yellow-400' : 'text-ghost-danger'}`}>
              {Math.round(fps)}
            </span>
          </div>

          {/* Bottom-left: Speed */}
          <div className="absolute bottom-3 left-3 flex items-end gap-1.5 px-3 py-2 rounded bg-black/70 backdrop-blur-sm border border-ghost-border">
            <span className="text-4xl font-black font-mono text-white leading-none text-glow-accent">
              {Math.round(speed)}
            </span>
            <span className="text-xs text-ghost-muted font-mono mb-1">km/h</span>
          </div>

          {/* Bottom-right: Compass */}
          <div className="absolute bottom-3 right-3 flex flex-col items-center px-3 py-2 rounded bg-black/70 backdrop-blur-sm border border-ghost-border">
            <span className="text-xs font-mono text-ghost-muted">HDG</span>
            <span className="text-lg font-bold font-mono text-ghost-accent">{formatHeading(heading)}</span>
            <span className="text-[10px] font-mono text-ghost-muted">{Math.round(heading)}°</span>
          </div>

          {/* Network quality corner badge */}
          <div className="absolute bottom-3 left-1/2 -translate-x-1/2 px-2.5 py-1 rounded bg-black/60 backdrop-blur-sm border border-ghost-border">
            <span className="text-[10px] font-mono text-ghost-muted tracking-widest uppercase">
              Net: <span className={networkQuality === 'excellent' ? 'text-ghost-success' : networkQuality === 'good' ? 'text-blue-400' : 'text-ghost-danger'}>
                {networkQuality.toUpperCase()}
              </span>
            </span>
          </div>
        </>
      )}

      {/* Corner decorations */}
      <CornerDecorations />
    </div>
  );
}

function CornerDecorations() {
  const c = 'absolute w-4 h-4 border-ghost-accent/50';
  return (
    <>
      <div className={`${c} top-2 left-2 border-t border-l`} />
      <div className={`${c} top-2 right-2 border-t border-r`} />
      <div className={`${c} bottom-2 left-2 border-b border-l`} />
      <div className={`${c} bottom-2 right-2 border-b border-r`} />
    </>
  );
}
