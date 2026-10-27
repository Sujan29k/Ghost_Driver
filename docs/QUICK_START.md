# GhostDriver: your Mac and your friend's GPU computer

The Mac runs the dashboard, backend and HTTPS tunnel. Your friend's computer
runs CARLA plus one Python sender with the trained YOLO and RAFT-Small models
from `sudip-work` (`00d414e`). The sender streams annotated video and an estimated
future view into your existing dashboard. No additional AI web server is needed.

## Your Mac

From the project folder, with Node 22.12+:

```sh
npm run setup
npm run doctor
npm run dev
```

Setup installs the locked dependencies and generates missing connection tokens
in `backend/.env`. Repeating it preserves your existing tokens and TURN settings.
Open **http://localhost:5173**, enter `DASHBOARD_TOKEN` from that file and connect.
For a built site instead, run `npm run build` followed by `npm start`, then open
**http://localhost:4000**. Use one startup method at a time.

In a second Mac terminal:

```sh
cloudflared tunnel --url http://127.0.0.1:4000
```

Privately give your friend the current HTTPS tunnel URL and `SENDER_TOKEN` from
`backend/.env`. Leave both terminals open. Only your Mac needs `DASHBOARD_TOKEN`.
TURN settings already in your local configuration are preserved; a fresh clone
needs its own TURN service settings in `backend/.env` for reliable video across
networks. `doctor` checks configuration and checkpoint hashes, not relay access.

## Transfer the integrated sender

Both computers need this integrated version. Until it has been committed and
pushed to `main`, pulling GitHub will not include the local changes. On your Mac:

```sh
npm run package:sender
```

Transfer `artifacts/ghostdriver-sender.zip` and extract it on the GPU computer.
The archive contains `carla-service`, both real model files and these guides.
It excludes credentials, environments and datasets. Run the following commands
from the extracted folder containing `carla-service`.

## Friend's Windows GPU computer

For **CARLA 0.9.15**, use Python 3.10 and the matching client
([official wheel list](https://pypi.org/project/carla/0.9.15/#files)). For another CARLA
release, use its supported Python interpreter and exactly matching client.
Install the simulator separately; the pip package is only the Python client.

```powershell
py -3.10 -m venv carla-service/.venv
.\carla-service\.venv\Scripts\python.exe -m pip install -r carla-service/requirements-ai.txt
.\carla-service\.venv\Scripts\python.exe -m pip install carla==0.9.15
.\carla-service\.venv\Scripts\python.exe -m pip check
.\carla-service\.venv\Scripts\python.exe carla-service/configure.py
```

The configuration prompt saves the Mac tunnel URL and sender token privately.
The initial profile enables YOLO, RAFT prediction at +250 ms, 30 cars, 5 bicycles
and 20 pedestrians. The actual counts depend on available spawn locations.
`AI_DEVICE=auto` selects the available device; install the appropriate CUDA
PyTorch build for your GPU using the [official selector](https://pytorch.org/get-started/locally/).

Start CARLA with rendering enabled in asynchronous mode, then:

```powershell
.\carla-service\.venv\Scripts\python.exe carla-service/check_setup.py
.\carla-service\.venv\Scripts\python.exe carla-service/bridge.py
```

Linux uses the same Python scripts with `carla-service/.venv/bin/python`.
The GPU computer needs no Node server, frontend, inbound port forwarding or
second copy of TURN credentials. Keep CARLA and the Python sender running.

## Connect and drive

1. On your Mac, connect to **Friend CARLA**. The dashboard reports model loading,
   CARLA connection, traffic spawning and camera readiness.
2. Select **Start stream** after **CARLA ready**. Wait for actual received frames.
3. The left video panel shows the observed camera with YOLO boxes; the right shows
   a labeled RAFT motion estimate. The estimate does not control the vehicle.
4. Select **Resume controls**, then use W/A/S/D and Space for emergency stop.
5. Check **Video RTT** (browser to sender), received FPS, packet loss and route.
   **Server RTT** is only the Mac browser-to-backend connection. Neither RTT is
   measured camera-to-display latency.
6. Stop video, enable **Test TURN only**, and start again. Confirm **TURN relay**
   and live frames to validate your actual relay credentials and both networks.

Camera/inference loss, disconnects and missing controls stop driving. Reconnecting
does not resume driving automatically. Stop the stream and then stop the bridge
with Ctrl+C so it can remove its own camera, vehicle and traffic actors.

## Later sessions and troubleshooting

Start `npm run dev` and the tunnel on your Mac. If the tunnel URL changes, rerun
`carla-service/configure.py` on the GPU computer; Enter keeps the existing token.
Then start CARLA and `bridge.py` again. Restarting the bridge reloads saved settings.

Set `PREDICTION=off` or `PREDICTION=farneback` in `carla-service/.env` for a lighter
pipeline. `AI_FPS`, `AI_DEVICE`, `PREDICTION_MS` and traffic counts are saved there
too; command-line flags override them. To diagnose the raw camera:

```sh
python carla-service/bridge.py --ai off --prediction off --traffic 0 --bicycles 0 --pedestrians 0
```

Detailed instructions: [AI and traffic](AI_TRAFFIC.md),
[two-network checks](CONNECTION_TEST.md), [validation record](AI_VALIDATION.md).
