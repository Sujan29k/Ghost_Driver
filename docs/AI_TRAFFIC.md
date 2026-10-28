# Run traffic, YOLO and RAFT with your existing dashboard

**Research profile update:** The default sender now uses the delayed-versus-predicted comparison, explicit driving modes, and scenario controls. Follow [TWO_COMPUTER_TEST.md](TWO_COMPUTER_TEST.md). Live-plus-future and optical-flow descriptions below refer to the legacy `--no-research` profile.

The integration uses `sudip-work` commit `00d414e` (fetched October 25, 2026).
The older `6f4b7c5` version was already merged into main; the newer AI work was
adapted selectively because its web stack uses a different protocol.

For the shorter everyday setup and a transferable sender archive, use
[QUICK_START.md](QUICK_START.md). The new `.env.example` enables the full YOLO +
RAFT profile. `configure.py` saves connection details and preserves later edits;
command-line flags override saved settings.

## What is included

| Part | How it runs here |
| --- | --- |
| Trained YOLOv8 `best.pt` | Default road-object detection, labels and boxes in live WebRTC video |
| Cars, bicycles, pedestrians | Spawned by `traffic.py`; actual counts appear on the dashboard |
| RAFT-Small source and checkpoint | `--prediction raft`, shown beside the live camera |
| Farneback prediction | `--prediction farneback`, a lighter alternative |
| Farneback motion colors | `--optical-flow`, a separate optional view |
| Existing React + Express/Socket.IO | Kept for authenticated discovery, controls, telemetry and WebRTC |

Only RAFT-Small is needed by the branch's live worker. The unused large RAFT
checkpoints, duplicate MJPEG/gateway servers, alternate frontend/backend,
Windows-specific multi-server launcher and evaluation outputs were not imported.
RAFT inference code is vendored with its license at the branch's pinned revision;
no Git submodule or Git LFS installation is needed on main. Both runtime weights
are real binary files. The YOLO SHA-256 matches the latest branch exactly.

The branch's depth tools inspect CARLA depth datasets; they do not contain a
Depth Anything inference model. Existing research datasets remain available but
are not loaded during startup. Unused Vite starter files and accidental empty
`pip`/`python` files were removed. `ghostdriver/integration.py` starts the same
unified bridge, avoiding a second vehicle/controller.

## Update both computers

Once these changes are committed and pushed, use `main` on both computers.
Preserve local `.env` files, environments and uncommitted work. On an existing
clean checkout:

```sh
git fetch origin
git switch main
git pull --ff-only origin main
```

Do not run the old `carla_gateway.py`, `carla_stream.py`, standalone integration
script or the other branch's `start.ps1` at the same time. Stop them first. If an
old process left actors or synchronous mode behind, restart CARLA once.

## Your Mac

From the repository root:

```sh
npm run setup
npm run dev
```

Keep a second terminal running:

```sh
cloudflared tunnel --url http://127.0.0.1:4000
```

Open http://localhost:5173 and authenticate with your dashboard token. Share the
current tunnel URL and sender token privately with your friend. A restarted
quick tunnel may have a new URL. No Python/CARLA/AI installation is needed on the
Mac for normal use.

## Friend's Windows GPU computer

Use one **Python 3.10** environment for the bridge, YOLO and RAFT when running
CARLA 0.9.15 on Windows x64. The official package includes a
[CPython 3.10 Windows wheel](https://pypi.org/project/carla/0.9.15/#files).
Do not reuse the other branch's Python 3.7 environment. If the simulator is a
different release, install its exactly matching client on a compatible Python
3.10+ interpreter instead.

If `carla-service/.venv` is absent, create it from the project root:

```powershell
py -3.10 -m venv carla-service/.venv
```

If it exists, check its version first. Preserve an incompatible environment and
create a new one at a different path, substituting that path below.

```powershell
.\carla-service\.venv\Scripts\python.exe --version
.\carla-service\.venv\Scripts\python.exe -m pip install -r carla-service/requirements-ai.txt
# This client version is for the CARLA 0.9.15 simulator only:
.\carla-service\.venv\Scripts\python.exe -m pip install carla==0.9.15
.\carla-service\.venv\Scripts\python.exe -m pip check
```

Use a CUDA-enabled PyTorch build matching the GPU from the
[official installation selector](https://pytorch.org/get-started/locally/) for GPU
inference. `--device cpu` also works, with lower throughput. Check CUDA using:

```powershell
.\carla-service\.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"
```

Start CARLA with rendering enabled and asynchronous mode. Keep `BACKEND_URL`
(current HTTPS tunnel address) and `SENDER_TOKEN` in `carla-service/.env`.
Then verify models and the local CARLA connection:

```powershell
.\carla-service\.venv\Scripts\python.exe carla-service/check_setup.py --prediction raft
```

This performs real model inference and checks simulator/client versions without
spawning vehicles. A pass is not a live video or cross-network test.

Start the live bridge:

```powershell
.\carla-service\.venv\Scripts\python.exe carla-service/bridge.py --name "Friend CARLA" --traffic 30 --bicycles 5 --pedestrians 20
```

These traffic counts and YOLO are already the defaults. The GPU computer needs
only CARLA and this Python process, not another Node server or frontend.

The new `.env.example` selects RAFT by default. To enable it explicitly on an
older configuration, stop the bridge with Ctrl+C and run:

```powershell
.\carla-service\.venv\Scripts\python.exe carla-service/bridge.py --name "Friend CARLA" --prediction raft --prediction-ms 250
```

The left panel is the observed YOLO camera; the right panel is a labeled motion
estimate 250 ms ahead. This is not a guaranteed future frame or a measured network
latency. It never controls the vehicle. Prediction uses actual CARLA frame-pair
timing, bounded displacement, and a maximum 320px inference width (minimum 128px
per dimension). Long frame gaps reset prediction buffering. No artificial delay
is added to driving commands.

`--prediction farneback` selects the lighter estimator. `--prediction off --optical-flow` shows
motion colors instead. Choose one secondary view. `--device 0` explicitly uses
CUDA; `--ai-fps 10` limits processing rate. Traffic count reduction can help CARLA
performance. Source frames older than two seconds stop the stream and latch brakes.

## Verify together

1. Check sender logs for model loading and actual spawned actor counts.
2. On the Mac, connect to **Friend CARLA**, wait for **CARLA ready**, start stream.
3. Confirm `YOLO | road objects` in the video, cars on the road, and class/confidence
   boxes. The scene panel separates spawned actors from objects detected in the
   current image. Zero detections does not mean zero actors in the map.
4. Traffic spawning prefers lane positions ahead of the ego and nearby map spawn
   points. Cars can move away before you connect; resume controls and drive to
   observe traffic. Occupied locations can reduce the requested count. The hood
   camera does not show the outside of your own car.
5. Test W/A/S/D, Space/emergency stop, focus loss, stream loss and reconnect.
   Reconnecting must leave controls stopped until explicit resume.
6. For RAFT, confirm the labeled estimated view and RAFT status in the dashboard.
7. Test TURN-only video using [CONNECTION_TEST.md](CONNECTION_TEST.md).
8. Stop stream, then Ctrl+C the bridge; check that its camera, car, background
   vehicles and walker controllers are removed before restarting.

The large-object image-area warning is advisory. It is not calibrated distance
or automatic braking. Manual driving and the existing watchdogs retain control.

Raw-camera troubleshooting, with only the base requirements installed:

```powershell
.\carla-service\.venv\Scripts\python.exe carla-service/bridge.py --ai off --prediction off --traffic 0 --bicycles 0 --pedestrians 0
```

## Validation

See [AI_VALIDATION.md](AI_VALIDATION.md) for the local test results and remaining
checks requiring the real Windows/CARLA computer and both networks.
