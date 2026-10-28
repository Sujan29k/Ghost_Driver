# CARLA research control and video protocol

This extends the existing authenticated Socket.IO rooms, ownership, signaling and shared ICE configuration. WebRTC still transports video directly or through TURN. Cloudflare exposes the signaling/backend service.

## Commands and acknowledged authority

An updated sender joins with `{mode:"carla", researchVersion:1}`. Only its authenticated owning dashboard can send `research:command {action,data}`. The backend validates and assigns a monotonic `commandId`, then sends `research:apply {action,data,commandId,previousMode}`. The sender captures its safety generation at queue entry and processes commands on a bounded operation worker. A newer stop cancels queued/in-progress transitions. The actuator loop remains independent.

The sender replies `{success:true,state}` only after application. State includes `version`, `commandId`, `generation`, `mode`, `stopped`, direction, reason, takeover, route, scenario, video configuration, policy and recording state. Failure replies contain a bounded explanation. The backend checks the acknowledgement sequence, safety epoch, ownership and driving authority before accepting it. Telemetry cannot acknowledge an active-mode transition or undo a backend stop. A timeout/disconnect/newer stop rejects the operation. No automatic resumption follows reconnection.

Commands:

| Action | Data |
| --- | --- |
| `mode` | `mode: STOPPED / MANUAL / AUTONOMOUS` |
| `direction` | `direction: forward / reverse` |
| `video` | `delayMs: 0/100/200/500/800`, `method: off/raft/farneback`, `view: compare/delayed/predicted/reference`, `reference: boolean` |
| `route` | `route: straight/left/right` lane-following junction preference |
| `scenario` | `operation: start/reset`, `name: none/normal/rain/landslide/flood/combined`, `severity: 1..3`, integer `seed`, `blockage: partial/full`, optional `weather` overrides |
| `policy` | bounded `stallSeconds`, `blockedSeconds`, `deviationMeters`, `deviationSeconds`, `weatherThreshold`, `hazardDistance` |
| `buffer` | `operation: clear` |
| `trial` | `operation: start`, `label`, `order`, `saveFrames`; or `operation: stop`, `outcome: completed/aborted/blocked` |

Weather overrides: `precipitation/wetness/puddles/fogDensity` (0–100), `sunAltitude` (-90–90), and local `friction` (0.05–2). Weather appearance and friction are separate effects. Omitted scenario operation defaults to `reset` for compatibility.

Mode/direction/video/route/policy/buffer changes and scenario reset/stop latch braking before applying. Only trial operations and **scenario start during active autonomy** preserve autonomous authority. This permits introducing a hazard during an autonomous run. They cannot resume a previously stopped vehicle. Scenario reset/stop additionally requires the ego below the low-speed threshold; click Stop driving and wait first. Starting severe weather while already stopped will require clearing its active trigger before autonomy can start.

Manual `control:direct` keeps nonnegative throttle, S as brake, steering and sequencing. Only MANUAL accepts it. R requests a direction change; the backend checks fresh reported speed and the sender checks actual speed (default 1 km/h). The selected CARLA `reverse` flag controls W acceleration; telemetry shows CARLA's actual gear. Changes clear held keys; the operator must release/repress a key after transitions. Space is the emergency shortcut outside text-entry fields; the explicit emergency button stays available.

AUTONOMOUS delegates to Traffic Manager (`set_path` on the installed map); manual actuator updates cease. `vehicle:supervise` is sent only with an owned video session and recent browser frame receipts. It is independent of the 750 ms manual-command watchdog. Loss of required monitoring or ownership stops the car. Emergency stop disables autopilot and latches full braking in every mode. Takeover triggers disable autopilot, show TAKEOVER_REQUESTED and apply the same latched braking fallback until explicit manual acknowledgement. An unanswered takeover stays stopped indefinitely. Return to autonomy requires Forward, low speed, fresh supervision, healthy sensors and no active nearby/scripted weather trigger.

## Video semantics and freshness

CARLA observations use simulation elapsed timestamps. History is bounded to 90 frames/128 MiB. For newest observed sender frame `r` at `t`, delay D selects the latest frame `d` at or before `t-D`, plus its earlier observation `p`. Flow uses only `p` and `d`. Horizon is `t-d.timestamp`; pair interval is `d.timestamp-p.timestamp`. Reference `r` is used only for display/evaluation. All composite panels share one target time, viewpoint and resolution. Skipped frames change the measured interval/horizon instead of assuming configured FPS.

Clears, configuration changes, timestamp rollback and gaps reset buffer epochs. A result begun before a reset cannot be published afterward. Reference capture age is checked after inference and again before sending/authorizing driving. Camera activity and intentional comparison buffering have separate status labels. Buffering stops driving but retains an existing WebRTC session during short refill periods; normal camera/decoded-frame watchdogs still close stalled streams. Predicted-only cannot authorize driving on an unavailable placeholder. No artificial delay is added to commands.

Injected delay is a configured simulation-time history offset, not measured one-way network latency. Horizon, prediction computation time, total processing time, browser/backend RTT, peer RTT, received FPS and packet loss remain distinct. No RTT/2 or configured FPS is presented as measured camera-to-display latency. Sender reference imagery also experiences processing/transmission/display delay on the Mac.

## Recording and evaluation

`carla-service/recordings/<trial-id>/manifest.json` records CARLA versions, model hashes/classes, installed package versions, sender source hashes, camera geometry, resolved map/route/scenario, seeds (including the separate background traffic seed), actual traffic counts, policy, video settings and trial order. JSONL events include commands, mode changes, sender-clock takeover trigger/notification receipt/manual acknowledgement/first action, sensor events, route progress, frame timestamps, network observations and outcomes. No connection credentials are recorded.

Video-worker `frame` rows record timing and computation cost. A separate bounded recording worker samples raw aligned images at most twice/second, computes metrics and emits `frame:evaluation` rows. Optional compressed NPZ files carry raw arrays plus frame-ID/timestamp/epoch alignment metadata. Dropped jobs are counted; the recorder never backpressures the video/control loops. Baseline-only skips unused inference; predicted-only skips unused YOLO. Recording still consumes resources, which must be held consistent across trial conditions.

Metrics use unannotated, same-size BGR uint8 images: MAE, PSNR, and Gaussian 11×11 sigma=1.5 SSIM. Identical images have infinite PSNR, encoded as null and counted separately. The evaluator verifies delay cutoff, history ordering, horizon/interval and saved-image identifiers before scoring. Delayed-only samples are reported independently; paired delayed and predicted means use **the same subset of reference images**. Worse-prediction cases are retained.

`senderMonotonicNs` is the common event clock. Browser timestamps/backend receipt times are separate clocks, never directly subtracted. Notification-receipt duration includes the signaling round trip; it is not the exact browser warning-display latency. The offline evaluator outputs separate visual and task sections and optionally a CSV row per trial. Supply multiple folders for repeated trials:

```powershell
.\carla-service\.venv\Scripts\python.exe carla-service\evaluate_trials.py carla-service\recordings\TRIAL_A carla-service\recordings\TRIAL_B --output comparison.json --csv comparison.csv
```

Executable synthetic-format examples are included as [JSON](examples/evaluation-example.json) and [CSV](examples/evaluation-example.csv); neither is a CARLA result.

Illustrative output structure (these are example numbers, not experimental results):

```json
{
  "trialId": "example",
  "trialOrder": 1,
  "visualReconstruction": {
    "alignedSamples": 10,
    "pairedSamples": 10,
    "delayedOnlySamples": 0,
    "pairedDelayed": {"mae": 8.4, "psnr": 25.1, "ssim": 0.81, "identicalImages": 0},
    "pairedPredicted": {"mae": 9.1, "psnr": 24.3, "ssim": 0.78, "identicalImages": 0},
    "predictionWorseCases": 6,
    "alignmentErrors": []
  },
  "taskPerformance": {"collisions": 0, "laneEvents": 1, "takeovers": []}
}
```

Live simulation remains asynchronous with no tick owner in this bridge. Seeds do not make it deterministic. Offline image evaluation does not provide deterministic driving replay. Visual reconstruction results cannot establish a driving benefit; use repeated, counterbalanced delayed-only/predicted-only operator trials with reference hidden and report failures as well as successes.
