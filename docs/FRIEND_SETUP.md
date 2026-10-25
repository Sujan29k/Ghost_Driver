# Your friend's GPU computer

Run CARLA and the Python bridge here. The React website and Node backend stay on the laptop. You do not need Node, cloudflared, public CARLA ports, or router port forwarding on this computer.

## 1. Start CARLA and match its Python client

Use your installed CARLA release and a Python environment supported by that release's Python wheel **and** the packages in `carla-service/requirements.txt`. Do not install an arbitrary latest `carla` package. The client and simulator versions must match exactly; the bridge checks and reports both versions before spawning anything.

Start CARLA normally in its default asynchronous mode, for example from its installation folder on Linux:

```sh
./CarlaUE4.sh -RenderOffScreen
```

On Windows, start the executable supplied by your CARLA release (for common UE4 releases, `CarlaUE4.exe`). Use the launch instructions for that release if the executable name differs. Do not enable CARLA's `no_rendering_mode`; the RGB camera needs rendering. Stop other scripts that put the world into synchronous mode, or restart the simulator before running this bridge.

Keep CARLA at `127.0.0.1:2000` from the bridge's perspective. Do not expose simulator ports 2000–2002 on the internet.

## 2. Install bridge dependencies

Copy/clone GhostDriver onto this computer. From its repository folder on Linux/macOS:

```sh
python3 -m venv carla-service/.venv
source carla-service/.venv/bin/activate
python -m pip install -r carla-service/requirements.txt
```

Windows PowerShell equivalent:

```powershell
py -m venv carla-service/.venv
carla-service/.venv/Scripts/Activate.ps1
python -m pip install -r carla-service/requirements.txt
```

Install the matching CARLA Python wheel supplied with your simulator release, using its actual path:

```sh
python -m pip install /path/to/CARLA/PythonAPI/carla/dist/carla-MATCHING-VERSION-AND-PYTHON.whl
```

Alternatively install `carla==<your simulator version>` from the package index if that exact release offers a wheel for your OS/Python combination. If no compatible wheel exists, create an environment matching the supplied wheel or build the matching CARLA client; do not work around a version mismatch. Verify the installed client:

```sh
python -c "import carla; print(carla.Client('127.0.0.1', 2000).get_client_version())"
```

The bridge uses CARLA's Python API for the RGB sensor and vehicle, NumPy for BGRA-to-BGR image data, aiortc/PyAV for WebRTC frames, and python-socketio/aiohttp for authenticated signaling.

## 3. Add the connection details

Copy the template:

```sh
cp carla-service/.env.example carla-service/.env
```

On PowerShell use `Copy-Item carla-service/.env.example carla-service/.env`.

Edit that file:

```dotenv
BACKEND_URL=https://the-address-from-your-friend.trycloudflare.com
SENDER_TOKEN=<the sender token shared privately by the laptop owner>
```

The URL contains no token or password. Use HTTPS for remote backends. You do not need the dashboard token. STUN and TURN, including TURN username/password, are fetched from the backend only after your sender token is accepted. Both WebRTC peers therefore use the same configured external ICE service.

## 4. Start the sender

With the virtual environment active, from the repository root:

```sh
python carla-service/bridge.py --host 127.0.0.1 --port 2000 --name "Friend CARLA"
```

The bridge registers as a sender, connects to CARLA, spawns a vehicle and attached 640×360 RGB camera at 30 FPS, and keeps the brakes on. The dashboard marks CARLA ready only while camera frames and telemetry are fresh. To try a different size:

```sh
python carla-service/bridge.py --width 1280 --height 720
```

The laptop owner can now connect and start video. Keep the sender and simulator running. For the first test, do not resume driving. Outbound HTTPS/WebSocket access to the tunnel and outbound access to the chosen STUN/TURN service are required on both networks.

The bridge retries unavailable backend connections and CARLA startup, and re-registers after reconnecting. It closes lost video sessions and brakes locally. The laptop owner must select the sender/start video again after a signaling disconnect, and explicitly resume controls later. If the tunnel address changes, edit `.env` and restart the bridge. Ctrl+C stops the bridge and removes the camera and vehicle it created.

Continue with [the shared verification checklist](CONNECTION_TEST.md). A real CARLA installation and the two-network route have not been validated by the repository's local tests.

References: [CARLA Python API](https://carla.readthedocs.io/en/latest/python_api/), [aiortc ICE configuration](https://aiortc.readthedocs.io/en/latest/api.html), [python-socketio client authentication and retries](https://python-socketio.readthedocs.io/en/stable/api_client.html).
