/**
 * VideoFeed — main camera / stream viewport.
 * Phase 1: shows a waiting state with futuristic overlay.
 * Phase 2: video element receives WebRTC srcObject from CARLA.
 */
import React, { useRef, useState } from 'react';
import { socket } from '../../services/socket';
import useVehicleStore from '../../store/vehicleStore';
import useWebRTC from '../../hooks/useWebRTC';
import { formatHeading } from '../../utils/formatters';

export default function VideoFeed() {
  const videoRef = useRef(null);
  const [previewMode, setPreviewMode] = useState('live');
  const {
    streamActive,
    vehicleConnected,
    connectedVehicleId,
    availableVehicle,
    speed,
    heading,
    fps,
    networkQuality,
    yoloStatus,
    yoloDetections,
    aiStatus,
    predictionHorizonMs,
    injectedLatencyMs,
    predictionMethod,
    predictionMetrics,
    inferenceMs,
    cameraDelayMs,
    controlDelayMs,
    setStreamActive,
    setWebRTCStatus,
    setInjectedLatencyMs,
  } = useVehicleStore();
  const isCarlaGateway = availableVehicle?.name === 'CARLA-Gateway';
  const detectionSummary = yoloDetections
    .slice(0, 2)
    .map((detection) => detection.class)
    .join(', ');
  const framePath = previewMode === 'predicted'
    ? 'predicted'
    : previewMode === 'delayed'
      ? 'delayed'
      : 'stream';
  const changeLatency = (latencyMs) => {
    setInjectedLatencyMs(latencyMs);
    socket.emit('latency:configure', { latencyMs });
  };
  const formatMetric = (value) => (
    value == null ? 'N/A' : Number.isFinite(value) ? value.toFixed(1) : 'MAX'
  );
  const { startStream, stopStream } = useWebRTC(videoRef);
  const handleStartStream = () => {
    if (isCarlaGateway) {
      setStreamActive(true);
      return;
    }
    startStream(connectedVehicleId);
  };

  return (
    <div className="ghost-panel relative flex-1 overflow-hidden scanlines">
      {isCarlaGateway ? (
        <img
          src={streamActive ? `http://localhost:5001/${framePath}.mjpg` : undefined}
          alt={`${previewMode} CARLA camera`}
          className={`absolute inset-0 w-full h-full object-contain ${streamActive ? 'opacity-100' : 'opacity-0'}`}
          onLoad={() => setWebRTCStatus('active')}
          onError={() => {
            setStreamActive(false);
            setWebRTCStatus('error');
          }}
        />
      ) : (
        <video
          ref={videoRef}
          autoPlay
          muted
          playsInline
          className={`absolute inset-0 w-full h-full object-cover ${streamActive ? 'opacity-100' : 'opacity-0'}`}
        />
      )}

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
              {isCarlaGateway
                ? `CARLA RGB · ${predictionMethod} +${predictionHorizonMs}ms`
                : 'WebRTC · CARLA Camera'}
            </p>
          </div>

          {vehicleConnected && (
            <button
              className="btn-ghost btn-accent text-xs"
              onClick={handleStartStream}
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
              {streamActive ? previewMode.toUpperCase() : 'STANDBY'}
            </span>
          </div>

          {/* Top-right: FPS */}
          <div className="absolute top-3 right-3 px-2.5 py-1.5 rounded bg-black/60 backdrop-blur-sm border border-ghost-border">
            <span className="text-[11px] font-mono text-ghost-muted">FPS </span>
            <span className={`text-[11px] font-mono font-bold ${fps >= 30 ? 'text-ghost-success' : fps >= 15 ? 'text-yellow-400' : 'text-ghost-danger'}`}>
              {Math.round(fps)}
            </span>
          </div>

          {isCarlaGateway && streamActive && (
            <div className="absolute top-12 left-1/2 z-10 flex -translate-x-1/2 rounded border border-ghost-border bg-black/80 p-0.5 font-mono text-[10px]">
              <button
                type="button"
                aria-pressed={previewMode === 'live'}
                className={`px-2 py-1 ${previewMode === 'live' ? 'text-ghost-accent' : 'text-ghost-muted'}`}
                onClick={() => setPreviewMode('live')}
              >
                LIVE
              </button>
              <button
                type="button"
                aria-pressed={previewMode === 'delayed'}
                className={`px-2 py-1 ${previewMode === 'delayed' ? 'text-ghost-accent' : 'text-ghost-muted'}`}
                onClick={() => setPreviewMode('delayed')}
              >
                DELAYED
              </button>
              <button
                type="button"
                aria-pressed={previewMode === 'predicted'}
                disabled={aiStatus !== 'connected'}
                className={`px-2 py-1 disabled:opacity-40 ${previewMode === 'predicted' ? 'text-ghost-accent' : 'text-ghost-muted'}`}
                onClick={() => setPreviewMode('predicted')}
                title={aiStatus === 'connected' ? `Show ${predictionMethod} prediction` : 'Waiting for the first prediction frame'}
              >
                PREDICTED
              </button>
            </div>
          )}

          {isCarlaGateway && streamActive && (
            <div className="absolute top-24 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1 rounded border border-ghost-border bg-black/80 p-1 font-mono text-[10px]">
              <span className="px-1 text-ghost-muted">RTT</span>
              {[0, 200, 500, 800].map((latencyMs) => (
                <button
                  key={latencyMs}
                  type="button"
                  aria-pressed={injectedLatencyMs === latencyMs}
                  className={`px-1.5 py-1 ${injectedLatencyMs === latencyMs ? 'text-ghost-accent' : 'text-ghost-muted'}`}
                  onClick={() => changeLatency(latencyMs)}
                  title={`Set round-trip latency to ${latencyMs} ms`}
                >
                  {latencyMs}
                </button>
              ))}
              <span className="px-1 text-ghost-muted">ms</span>
              <span className="px-1 text-ghost-muted">
                VIDEO {cameraDelayMs} / CTRL {controlDelayMs}
              </span>
            </div>
          )}

          {isCarlaGateway && (
            <div className="pointer-events-none absolute top-12 left-3 z-10 px-2.5 py-1 rounded bg-black/70 border border-ghost-border text-[10px] font-mono">
              <span className="text-ghost-success">YOLO</span>
              <span className="text-ghost-text"> {yoloStatus === 'connected' ? `${yoloDetections.length} OBJECTS` : 'OFFLINE'}</span>
              {detectionSummary && <span className="text-ghost-muted"> · {detectionSummary}</span>}
            </div>
          )}

          {isCarlaGateway && streamActive && predictionMetrics && (
            <div className="pointer-events-none absolute bottom-12 right-3 z-10 rounded border border-ghost-border bg-black/80 px-2 py-1 font-mono text-[9px] text-ghost-muted">
              <div>{predictionMethod} · {Math.round(inferenceMs)}ms</div>
              <div>PSNR D/F/R {formatMetric(predictionMetrics.delayedPsnr)} / {formatMetric(predictionMetrics.farnebackPsnr)} / {formatMetric(predictionMetrics.raftPsnr)} dB</div>
              <div>SSIM D/F/R {formatMetric(predictionMetrics.delayedSsim)} / {formatMetric(predictionMetrics.farnebackSsim)} / {formatMetric(predictionMetrics.raftSsim)}</div>
            </div>
          )}

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
