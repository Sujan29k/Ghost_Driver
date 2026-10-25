# Friend's CARLA setup checklist

Follow this file on the GPU computer that will run CARLA. Run commands one at a time. Replace placeholders with your actual values.

Your computer runs CARLA and the Python bridge. The laptop owner runs the dashboard, backend, and tunnel. You do not need Node.js or cloudflared.

## 1. Send your system details to the laptop owner

Fill this in first:

```text
Operating system and version:
CARLA simulator version:
Python version:
CARLA launches and loads a world: Yes / No
```

Check Python using `python --version` (or `python3 --version` on Linux). Identify the CARLA version from the release you installed. Start CARLA normally and confirm it loads a world before continuing.

You need:

- A GPU computer on which your CARLA release runs successfully.
- A copy of the GhostDriver project, including `carla-service`.
- A Python version supported by both your CARLA client wheel and the bridge dependencies.
- The laptop owner's current backend tunnel address and sender token, shared privately.
- Outbound network access to the backend and the configured STUN/TURN service.

Do not forward CARLA ports 2000–2002 or expose them to the internet.

## 2. Create a Python environment

Open a terminal in the main GhostDriver project folder, the folder containing `carla-service`.

Use the Python interpreter that matches your CARLA wheel. If your default Python is incompatible, select the correct installed interpreter when creating the environment.

### Windows PowerShell

```powershell
py -m venv carla-service/.venv
.\carla-service\.venv\Scripts\Activate.ps1
python -m pip install -r carla-service/requirements.txt
```

If PowerShell blocks activation, you can run the environment's interpreter directly instead. Use this executable in place of `python` for every remaining command:

```powershell
.\carla-service\.venv\Scripts\python.exe -m pip install -r carla-service/requirements.txt
```

### Linux

```sh
python3 -m venv carla-service/.venv
source carla-service/.venv/bin/activate
python -m pip install -r carla-service/requirements.txt
```

## 3. Install the matching CARLA Python client

The Python client and simulator versions must match exactly. Do not install an arbitrary latest `carla` package.

Install the matching wheel supplied with your CARLA release, replacing the example path:

```sh
python -m pip install "/actual/path/to/CARLA/PythonAPI/carla/dist/matching-carla-wheel.whl"
```

Alternatively, if the exact release has a compatible package for your OS and Python, install it using `python -m pip install carla==VERSION`, replacing `VERSION` with your simulator version.

If pip reports an unsupported wheel or no matching distribution, check the wheel's OS, Python version, and architecture. Use a compatible Python environment; do not substitute a different CARLA release.

## 4. Start CARLA and check the connection

Start CARLA from its installation folder. For common UE4 releases:

- Windows: launch `CarlaUE4.exe`.
- Linux: run `./CarlaUE4.sh -RenderOffScreen`.

If your release uses a different executable, follow its launch instructions. Keep CARLA running in default asynchronous mode. Stop other scripts that enable synchronous mode, or restart CARLA. Do not enable `no_rendering_mode`: the RGB camera needs rendering.

In your GhostDriver terminal, with the Python environment active, run:

```sh
python -c "import carla; c=carla.Client('127.0.0.1',2000); c.set_timeout(10.0); print('Client:', c.get_client_version()); print('Server:', c.get_server_version()); print('Map:', c.get_world().get_map().name)"
```

Continue only when the client and server versions match and a map name prints. Send this output to the laptop owner if you need help.

## 5. Configure your backend connection

Create `carla-service/.env` from the template only if it does not already exist. Otherwise, edit the existing file.

Windows PowerShell:

```powershell
Copy-Item carla-service/.env.example carla-service/.env
```

Linux:

```sh
cp carla-service/.env.example carla-service/.env
```

Put these settings in that file:

```dotenv
BACKEND_URL=https://car-licenses-stick-closest.trycloudflare.com
SENDER_TOKEN=REPLACE_WITH_SENDER_TOKEN_SHARED_PRIVATELY
```

The address above was supplied on October 25, 2026. It is temporary and works only while the laptop owner's tunnel is running. Ask for the current address if the tunnel has restarted.

The sender token must match `SENDER_TOKEN` in the laptop owner's `backend/.env`. It is not the dashboard token, TURN password, or provider API key. Do not commit your `.env` or share its contents publicly.

You do not need to configure TURN credentials on your computer; the authenticated backend supplies them automatically.

Open this URL in your browser, replacing its hostname if the tunnel has changed:

```text
https://car-licenses-stick-closest.trycloudflare.com/api/health
```

Expected response:

```json
{"success":true}
```

If that fails, ask the laptop owner to confirm that `npm run dev` and cloudflared are running. A successful health check proves backend reachability, not authentication or video.

## 6. Start the bridge

With CARLA running, run this from the main GhostDriver folder in your active Python environment:

```sh
python carla-service/bridge.py --host 127.0.0.1 --port 2000 --name "Friend CARLA"
```

Keep this terminal and CARLA running. The bridge creates a vehicle and a 640×360 camera configured for 30 FPS, initially with brakes applied. Actual received FPS is measured on the laptop.

Tell the laptop owner the bridge is running. They should wait for **Sender connected**, then **CARLA ready**, select **Connect**, and select **Start stream**.

Do not begin driving until they confirm actual CARLA video and nonzero received FPS.

## 7. Help verify driving and recovery

Coordinate these tests with the laptop owner. Observe the vehicle locally when possible, especially when the dashboard is disconnected.

- After video works, the laptop owner clicks **Resume controls** and tests short W/A/S/D presses. W accelerates, A/D steer, and S brakes.
- They test Space or **Emergency stop**. Confirm braking and that driving requires an explicit **Resume controls** afterward.
- They switch away from the dashboard while moving slowly. Confirm braking on focus loss.
- They close the dashboard while moving slowly. Confirm braking on disconnection.
- Stop the bridge with **Ctrl+C**, then start it again with the same command. The dashboard must reconnect and restart video; controls must remain stopped until explicitly resumed.
- The laptop owner stops video, selects **Test TURN only**, and restarts video. Success requires real video, nonzero FPS, and a **TURN relay** route.

If the tunnel address changes, edit `BACKEND_URL` and restart the bridge. When finishing, press **Ctrl+C** in the bridge terminal so it can remove its camera and vehicle.

## 8. Report results

Send this completed checklist to the laptop owner. Do not include secrets.

```text
OS:
Python version:
CARLA server version:
CARLA client version:
Map loaded:
Public backend health check: Pass / Fail
Bridge connects: Pass / Fail
Dashboard shows CARLA ready: Pass / Fail
Real video received: Pass / Fail
Received FPS range (from laptop):
Packet loss (from laptop):
Video route (from laptop):
Emergency-stop braking: Pass / Fail
Focus-loss braking: Pass / Fail
Dashboard-disconnect braking: Pass / Fail
Bridge restart recovery time:
Controls remain stopped after restart: Pass / Fail
TURN-only video: Pass / Fail
Errors or connection failures:
Actual video delay: Not measured / measurement and method
```

The dashboard's Server RTT measures its connection to the laptop's local backend. It does not measure remote video delay. Leave actual video delay as "Not measured" unless measured separately.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| `No module named carla` | Install the matching client in the same Python environment used to run the bridge. |
| CARLA connection timeout | Simulator running, world loaded, local port 2000, no conflicting synchronous-mode script. |
| Client/server version mismatch | Install the exact matching CARLA client. |
| Backend authentication fails | Correct sender token, no accidental whitespace, restart bridge after editing `.env`. |
| Backend unreachable | Current tunnel address; laptop application and tunnel both running. |
| Sender connected but CARLA not ready | Check bridge logs, rendered camera frames, simulator version and asynchronous mode. |
| Video fails but bridge connects | Laptop owner checks TURN settings and both networks' outbound connectivity. |
| Controls stopped after reconnecting | Expected: reconnect video, release held keys, explicitly resume controls. |

Additional project guides: [Friend setup](FRIEND_SETUP.md) and [Connection test](CONNECTION_TEST.md).
