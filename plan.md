# GhostDriver runnable web and CARLA handoff plan

## Objective

Make a fresh checkout runnable without CARLA, with the same video/control/telemetry contract available to a friend running CARLA. The default demo will use a browser-generated road scene, so it needs no GPU, webcam permission, model weights, MP4, or Python installation. Existing research scripts will be preserved. Frame prediction remains a later research step; the UI will identify demo and received video honestly.

## Required services

1. React/Vite operator dashboard (development port 5173).
2. Node/Express/Socket.IO backend (port 4000): discovery, exclusive operator ownership, commands, telemetry, and WebRTC signaling. No database required.
3. One vehicle provider: the included browser mock tab, or the optional Python CARLA bridge using aiortc.
4. CARLA simulator (normally port 2000), only on the friend's CARLA-capable computer. Its Python client version must match the simulator.

Production web builds will also be served by Node, reducing the web stack to one process. Internet deployment, authentication, TURN hosting, and a validated prediction algorithm are outside this local/trusted-network prototype.

## Implementation sequence

1. Add portable root npm commands, dependency setup, environment examples, and a non-destructive launcher. Replace hardcoded browser localhost URLs with same-origin routing.
2. Replace backend simulated state with a vehicle/session registry. Register providers, replay discovery to late clients, claim/release one vehicle, forward validated full-state controls, relay actual telemetry and scoped WebRTC messages, stop/release on disconnect, and expire stale commands. Keep health reporting truthful.
3. Connect dashboard state to actual acknowledgements. Repair streaming lifecycle and ICE buffering. Send combined key state at a fixed rate, release on blur/disconnect, latch emergency stop until explicit resume, measure browser/backend RTT, and read video statistics from WebRTC.
4. Replace the webcam-only simulator page with a self-contained canvas road demo. It will respond to controls, emit mock telemetry, send canvas video over WebRTC, handle stream stop/reconnect, and stop motion when commands expire.
5. Add an optional Python CARLA bridge, isolated from existing YOLO/research scripts. It will stream the newest RGB frame, apply commands with a local timeout, emit actual telemetry, implement the same signaling contract, and clean up only its own actors. Document Python dependencies and matching CARLA installation separately.
6. Add integration tests for discovery, ownership, control validation/forwarding, telemetry, signaling, disconnects, and emergency stop. Build the frontend, syntax-check Python without running CARLA, and exercise the browser demo if browser tooling is available.
7. Write the fresh-checkout runbook and friend handoff instructions, including service responsibilities, ports, local/LAN setup, limitations, and the exact checks completed.

## Acceptance criteria

- `npm run setup` installs locked web dependencies; `npm run dev` starts both web services and shuts down only its own children.
- A user opens the dashboard and mock vehicle tab, connects, starts video, steers/brakes, sees provider telemetry, and stops/reconnects without stale sessions.
- Browser controls do not depend on OS key repeat; emergency stop stays active until explicitly resumed; loss of control messages stops the provider.
- Late dashboard connections discover existing providers, and a second operator cannot control an owned vehicle.
- The built dashboard runs through `npm start` after `npm run build`.
- CARLA instructions do not imply that CARLA itself, GPU drivers, or a matching Python wheel can be installed automatically on every machine.
- No latency-compensation accuracy or CARLA runtime claim is made without measurement.

## Progress

- [x] Inspect current implementation and write this plan before implementation.
- [x] Portable setup and launcher.
- [x] Backend vehicle/session contract.
- [x] Dashboard lifecycle and controls.
- [x] Browser mock vehicle.
- [x] Optional CARLA bridge.
- [x] Tests and verification.
- [x] Handoff documentation.


## Completed implementation and verification

- Added root npm setup/dev/build/start/test commands, same-origin routing, environment examples, and a multi-page build containing the dashboard and browser vehicle provider.
- Replaced disconnected backend scaffolding with one tested vehicle/session hub. Added provider telemetry, exclusive ownership, sequenced controls, a latched stop, timeouts, scoped signaling, late discovery, and re-registration after provider timeout.
- Implemented dashboard lifecycle, combined 20 Hz key state, window focus braking, explicit resume, WebRTC ICE buffering, session cleanup, received-video statistics, and monotonic server RTT.
- Added a canvas demo requiring no Python, CARLA, models, or webcam; preserved the existing research scripts.
- Added `carla-service/bridge.py`, requirements, and an independent tested command watchdog. Real CARLA execution remains unverified because no CARLA server is available on this device.
- Documented services, fresh-checkout startup, the optional CARLA setup, LAN configuration, current limitations, and the provider protocol.
- The clean-install check revealed 1,392 committed backend dependency files. Removed `backend/node_modules` from Git tracking while retaining local installed dependencies. This index-only cleanup is staged; application changes remain available for normal review/commit. Lockfiles replace committed dependencies as the portable installation record.

Checks completed:

- `npm run setup`: passed (both projects installed from lockfiles). Compatible audit updates were then applied and final package/lockfile consistency checked.
- `npm test`: five backend integration tests passed after dependency updates.
- `npm run test:browser`: production build passed; Chrome end-to-end test passed with actual WebRTC frames, combined keys, stop/resume, explicit blur/focus events, stream restart, reconnect, late discovery, and provider disappearance. Explicit focus events are used because headless Chrome emulates focus for both test pages.
- Development launcher: started Node and Vite on isolated ports; the demo page and proxied health endpoint responded; shutdown released both ports.
- `python -m unittest discover -s carla-service/tests`: two watchdog/validation tests passed.
- CARLA bridge parsed successfully; `python carla-service/bridge.py --help` works without optional dependencies.
- `git diff --check`: passed.
- Dependency audit: backend zero advisories; seven remain in Tailwind 3 build tools (five high, two moderate). A forced Tailwind major migration is outside this implementation and is documented in README.md.

No CARLA runtime, end-to-end video latency, prediction accuracy, or public internet deployment has been claimed as verified. Test services have been stopped. No commit or push has been made.
