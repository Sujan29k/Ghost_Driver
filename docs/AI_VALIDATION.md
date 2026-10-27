# AI integration validation — October 25, 2026

Source branch: `origin/sudip-work` at `00d414e`. Integration is selective;
main retains its existing authenticated React/Socket.IO/WebRTC stack.

## Passed locally

- `npm test`: 13 backend tests, including bounded YOLO, prediction and traffic
  telemetry, startup phases, ownership, authentication, signaling and control watchdogs.
- `npm run test:browser`: production build and 3 Chrome tests passed. The
  explicitly synthetic sender exercises received video, the new scene/RAFT
  labels, controls, emergency stop, focus loss, video loss and reconnect.
  AI metadata in this browser test is a fixture, not inference. A separate test
  verifies CARLA startup messages without manufacturing camera video.
- Python unittest: 16 tests passed without skips in the temporary AI environment.
  Includes real aiortc encoding/decoding and Socket.IO with a stubbed CARLA API,
  raw and processed frames, stalled inference, camera loss, braking and cleanup.
  Also covers detection filtering, motion dimensions, prediction direction and
  frame-time scaling, long gaps, LFS pointer errors, traffic ownership, saved GPU
  profiles, command-line overrides and invalid backend/configuration rejection.
- Real bundled YOLO + RAFT-Small inference on CPU passed using:

  ```sh
  python carla-service/check_setup.py --models-only --prediction raft --device cpu --image carla-service/ghostdriver/dataset/clear_traffic/000000.jpg --output /tmp/ghostdriver-integrated-models.jpg
  ```

  YOLO detected one car at 0.76 confidence. RAFT loaded its actual checkpoint and
  produced a finite 1280×360 combined image. The test repeats the saved image as
  a frame pair; it verifies loading/inference/rendering, not prediction accuracy.
  The latest repeated check saved `/tmp/ghostdriver-final-ai-check.jpg` and took
  206.7 ms for one complete processing call on this Mac CPU; this is not
  a sustained FPS benchmark or a Windows/CUDA performance claim.
- Python source compilation and dependency-free bridge `--help` passed.
- `npm run configure` and `npm run doctor` passed with the existing private
  backend settings preserved and demo mode disabled. A separate temporary-folder
  check verified fresh distinct token generation, private file permissions,
  repeat setup without changes, no secrets in output, and preserving invalid
  existing settings while reporting an error.
- The new GPU `.env.example` selects YOLO + RAFT, with persistent device, inference
  FPS, prediction horizon and traffic settings. `configure.py` accepts the Mac's
  URL/token without placing the token in shell arguments.
- The friend configuration helper passed an isolated fresh-file check and a
  repeat URL update, preserving its saved token and inference settings.
- `npm run package:sender` created a 9.3 MB runtime archive. Its 33 entries were
  checked for archive integrity, matching model bytes, Python syntax, a working
  extracted `bridge.py --help`, and absence of local credentials and datasets.
- The configured external TURN service accepted the existing credentials and
  returned a relay candidate during a real aiortc ICE gathering check from the
  Mac. This verifies relay allocation, not video connectivity on both networks.
- Live local dashboard/backend HTTP checks and the public Cloudflare tunnel
  health check passed. A Python sender authenticated over the public HTTPS
  WebSocket and fetched the shared ICE configuration successfully.
- That live check exposed an unpopulated Python default certificate store.
  The sender now adds the maintained `certifi` CA bundle to its default SSL
  context, retaining normal certificate/hostname verification. All 16 Python
  tests passed again after the transport-session change. The tunnel briefly
  reconnected before the successful public check; quick tunnels remain temporary.
- Runtime checkpoint hashes match the latest branch's LFS records:
  - YOLO best.pt: `82441f63220c007b654f201cb55037181e359e85b0bfe6b5ccd55daf0971279e`
  - RAFT-Small: `c7d41b9cc88442bb8aa911dbb33086dac55a226394b142937ff22d5578717332`

Local environment: Node 25.3.0; temporary Python 3.14 environment with torch
2.14.1, Ultralytics 8.4.188 and aiortc 1.15.0. The Mac emitted duplicate
AVFoundation class warnings when importing OpenCV and PyAV; inference and tests
completed. Production setup on CARLA 0.9.15 uses Python 3.10 on Windows/Linux x64,
not this Mac test interpreter.

The sandbox initially blocked localhost test sockets. Backend, Python integration
and Chrome checks passed when rerun with permission for local networking.

## Requires the two real computers

- Compatible Windows Python/CARLA/CUDA installation and model throughput.
- Actual traffic, bicycles and walker behavior, camera field of view and cleanup.
- Annotated live CARLA video reaching the Mac through the real network.
- Credentialed TURN-only operation and latency under network loss.
- Practical driving, stopping and reconnect behavior with the simulator running.

No real CARLA server or friend's computer was available in this workspace.
Follow [AI_TRAFFIC.md](AI_TRAFFIC.md) for installation and the live checks.
