# Friend's computer: CARLA setup and agent prompt

For the integrated traffic, YOLO and RAFT setup, start with [AI_TRAFFIC.md](AI_TRAFFIC.md). Use Python 3.10+; for CARLA 0.9.15 on Windows x64, use Python 3.10 and the matching `carla==0.9.15` client. The older Python 3.7 environment is incompatible with this bridge.

Run **CARLA and the Python bridge** on this GPU computer. The laptop owner runs the React dashboard, Node backend, and Cloudflare tunnel on their Mac. Prepare the project, Python environment, and simulator while they prepare the backend; their current tunnel URL and sender token are needed for the remote connection steps.

See [Steps to run on both computers](STEPS_TO_RUN.md) for the coordinated guide. To have an agent perform this setup, copy the [prompt at the end](#copyable-prompt-for-the-agent-on-this-computer).

## 1. Collect the required information

Record these details without putting secrets in this document:

```text
Operating system and version:
CPU architecture:
GPU model and driver:
Available disk space:
GhostDriver project folder:
CARLA installation folder (or not installed):
CARLA simulator version:
Installed Python versions:
CARLA loads a world: Yes / No
```

The laptop owner must privately provide their **current backend HTTPS URL** and **SENDER_TOKEN**. You do not need their dashboard token, TURN password, or Cloudflare credentials; ICE settings are supplied by the backend after authentication.

You do not need Node.js, npm, cloudflared, or research datasets. The live bridge uses YOLO and the bundled best.pt checkpoint; install requirements-ai.txt. Do not expose CARLA ports 2000–2002 or configure router port forwarding.

Use only the commands for your OS below. Replace example installation paths and uppercase placeholders with actual values.

## 2. Get the project

If the current project already exists on this computer, open its folder and skip cloning. Preserve local work.

Otherwise, from the parent folder where you want the project:

```sh
git clone https://github.com/Sujan29k/Ghost_Driver.git
cd Ghost_Driver
```

For a private repository, obtain repository access and authenticate with GitHub. Alternatively, receive a private copy of the current project excluding `.env`, `node_modules`, and virtual environment folders.

All subsequent **project commands** run from the folder containing `carla-service`. CARLA itself runs from its separate installation directory.

Windows PowerShell:

```powershell
Get-Item carla-service/bridge.py, carla-service/requirements-ai.txt, carla-service/.env.example
```

Linux:

```bash
ls carla-service/bridge.py carla-service/requirements-ai.txt carla-service/.env.example
```

## 3. Choose compatible CARLA and Python versions

Check installed Python versions.

Windows PowerShell:

```powershell
py --list
py --version
```

Linux:

```bash
python3 --version
```

Identify the installed CARLA release and inspect its client files. Common paths are shown below; use the actual location for your release.

Windows example:

```powershell
Get-ChildItem "C:\CARLA\PythonAPI\carla\dist"
```

Linux example:

```bash
ls "/actual/path/to/CARLA/PythonAPI/carla/dist"
```

The simulator and Python client versions must match **exactly**. The wheel must match the interpreter, OS, and CPU architecture. For example, `cp310` targets CPython 3.10; it is not a recommendation to use 3.10 for every release. The interpreter must also support `carla-service/requirements-ai.txt`.

If CARLA or compatible Python is absent:

1. Identify a packaged CARLA release compatible with this OS/GPU and with a client supported by the bridge dependencies.
2. Consult the official documentation for that release, including disk, GPU, and runtime prerequisites.
3. Download and extract the simulator into a dedicated folder, install its required runtimes, and verify it launches.
4. Install the Python interpreter matching the client wheel before creating the environment.

`pip install carla` installs the Python client, **not the simulator**. Do not blindly install the latest client. The [CARLA 0.9.15 package guide](https://carla.readthedocs.io/en/0.9.15/start_quickstart/) is a version-specific reference; select documentation matching your actual release.

## 4. Create the virtual environment and install dependencies

If `carla-service/.venv` exists, inspect its interpreter and reuse it if compatible. Do not silently overwrite an incompatible environment.

### Windows PowerShell

If the default `py` interpreter is compatible:

```powershell
py -m venv carla-service/.venv
.\carla-service\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r carla-service/requirements-ai.txt
```

If the actual wheel requires an installed Python 3.10, replace the first command with this example before creating the environment:

```powershell
py -3.10 -m venv carla-service/.venv
```

If activation is blocked, use the interpreter directly instead of changing global execution policy:

```powershell
.\carla-service\.venv\Scripts\python.exe -m pip install --upgrade pip
.\carla-service\.venv\Scripts\python.exe -m pip install -r carla-service/requirements-ai.txt
```

For **every later command** starting with `python`, substitute `.\carla-service\.venv\Scripts\python.exe` if activation was skipped.

### Linux

If `python3` is compatible:

```bash
python3 -m venv carla-service/.venv
source carla-service/.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r carla-service/requirements-ai.txt
```

Otherwise substitute the correct installed interpreter in the first command, such as `python3.10` when required by the actual wheel.

If Ubuntu/Debian cannot create a venv for the default system Python:

```bash
sudo apt update
sudo apt install python3-venv
```

Then retry. A separately installed interpreter may need its corresponding version-specific venv package. Install project packages inside the venv; do not use `sudo pip`.

## 5. Install and verify the matching CARLA client

Use the actual wheel path.

Windows example:

```powershell
python -m pip install "C:\CARLA\PythonAPI\carla\dist\ACTUAL_MATCHING_WHEEL_FILENAME.whl"
```

Linux example:

```bash
python -m pip install "/actual/path/to/CARLA/PythonAPI/carla/dist/ACTUAL_MATCHING_WHEEL_FILENAME.whl"
```

Alternatively, if the package index offers the exact release for your OS/Python combination:

```sh
python -m pip install "carla==EXACT_SIMULATOR_VERSION"
```

Use one method. If no compatible wheel exists, resolve interpreter/platform compatibility or follow the matching release's client build procedure. Do not bypass version checks.

Verify:

```sh
python --version
python -m pip check
python -c "import carla, aiortc, av, socketio, aiohttp, numpy, dotenv; print('Bridge imports OK')"
python carla-service/bridge.py --help
```

Expected: no broken package requirements, `Bridge imports OK`, and bridge usage information.

## 6. Start CARLA in a separate terminal

For common UE4 packages:

Windows PowerShell:

```powershell
cd "C:\CARLA"
.\CarlaUE4.exe
```

Linux:

```bash
cd "/actual/path/to/CARLA"
./CarlaUE4.sh -RenderOffScreen
```

Use the actual installation path and release-specific launcher. Wait for the world to load and keep CARLA running.

- Use default **asynchronous mode**. Coordinate stopping other synchronous controllers or restarting their simulator session.
- Keep rendering enabled. `no_rendering_mode` prevents useful RGB camera output; offscreen rendering does not disable rendering.
- The bridge connects locally to `127.0.0.1:2000`. Keep simulator ports private.

## 7. Verify the local simulator connection

Return to the **GhostDriver project terminal**, using the active venv or its explicit interpreter:

```sh
python -c "import carla; c=carla.Client('127.0.0.1',2000); c.set_timeout(10.0); print('Client:', c.get_client_version()); print('Server:', c.get_server_version()); print('Map:', c.get_world().get_map().name); print('Synchronous:', c.get_world().get_settings().synchronous_mode); print('No rendering:', c.get_world().get_settings().no_rendering_mode)"
```

Continue only when client/server versions match exactly, a map name prints, and both `Synchronous` and `No rendering` are `False`.

A timeout here is a local simulator problem. Resolve it before troubleshooting the tunnel. Successful imports alone do not prove the simulator works.

## 8. Configure the connection to the laptop

The laptop owner must run their backend and tunnel. Obtain the HTTPS URL from their **current** tunnel session and their sender token privately.

Create your configuration only if it does not already exist.

Windows PowerShell:

```powershell
if (!(Test-Path "carla-service/.env")) {
    Copy-Item "carla-service/.env.example" "carla-service/.env"
}
notepad carla-service/.env
```

Linux:

```bash
if [ ! -f carla-service/.env ]; then
    cp carla-service/.env.example carla-service/.env
fi
nano carla-service/.env
```

Save actual values:

```dotenv
BACKEND_URL=https://ACTUAL-CURRENT-TUNNEL.trycloudflare.com
SENDER_TOKEN=ACTUAL_SENDER_TOKEN_SHARED_PRIVATELY
```

In `nano`, save with **Control+O**, Enter, then exit with **Control+X**.

Use the base HTTPS URL without `/api/health`, query parameters, or credentials. The sender token must match the laptop's `SENDER_TOKEN`, not its dashboard token.

Do not commit `.env`, paste secrets into agent prompts, or put tokens in command arguments. If an agent is helping, enter the token directly into the local file or through its secure secret-input facility. TURN settings are fetched automatically; both networks need outbound HTTPS/WebSocket and configured STUN/TURN access.

## 9. Check backend reachability

Replace the hostname with the actual current one.

Windows PowerShell:

```powershell
Invoke-RestMethod "https://ACTUAL-CURRENT-TUNNEL.trycloudflare.com/api/health"
```

Expected: `success` is `True`.

Linux:

```bash
curl --fail --show-error --max-time 15 "https://ACTUAL-CURRENT-TUNNEL.trycloudflare.com/api/health"
```

Expected:

```json
{"success":true}
```

If it fails, have the laptop owner check their backend, tunnel, and URL. A login/challenge HTML page is not success; the Python client needs noninteractive access.

This checks reachability only, not sender authentication, camera readiness, or video.

## 10. Start the bridge

With CARLA running, from the project root in the active environment:

```sh
python carla-service/bridge.py --host 127.0.0.1 --port 2000 --name "Friend CARLA"
```

Windows without activation:

```powershell
.\carla-service\.venv\Scripts\python.exe carla-service/bridge.py --host 127.0.0.1 --port 2000 --name "Friend CARLA"
```

Keep this terminal and CARLA running. Run only one bridge instance unless intentionally testing multiple senders.

The bridge registers with the backend, connects to CARLA, and creates a vehicle with a 640×360 RGB camera configured for 30 FPS. Brakes start applied. Received FPS is measured on the laptop's dashboard.

Tell the laptop owner the bridge has started. Share relevant errors with secrets removed.

## 11. Verify video and controls together

The laptop owner should:

1. Open `http://localhost:5173` on their Mac and authenticate with their dashboard token.
2. Wait for **Friend CARLA** and **CARLA ready**.
3. Click **Connect**, then **Start stream**.
4. Confirm actual CARLA scenery, **LIVE CARLA VIDEO**, and nonzero received FPS.
5. Stop video, enable **Test TURN only**, and start again. Confirm actual frames and **TURN relay**.
6. Stop video, disable **Test TURN only**, and start again for normal operation.

Keep controls stopped until real video works. Then coordinate driving while you observe:

- The laptop owner clicks **Resume controls** and tests brief W/A/S/D presses.
- W accelerates, A/D steer, and S brakes; S is not reverse.
- Space or **Emergency stop** stops controls until explicitly resumed.
- Check braking on focus loss and bridge/signaling disconnection.
- After reconnection, select the sender and start video again. Controls must stay stopped until deliberately resumed.

A healthy HTTP endpoint, configured credentials, or a running bridge does not prove video works. Real video and TURN-only verification require both computers. See [the full connection checklist](CONNECTION_TEST.md).

## 12. Troubleshooting

| Problem | Action |
| --- | --- |
| Python or Git command missing | Install the required tool for this OS; choose Python based on client wheel compatibility. |
| PowerShell blocks activation | Use `.\carla-service\.venv\Scripts\python.exe` directly. |
| Unsupported wheel / no matching distribution | Check release, Python ABI, OS, architecture, and bridge requirements. |
| `ModuleNotFoundError` | Use the venv interpreter; install requirements and the matching CARLA client there. |
| CARLA timeout | Check simulator startup and local port 2000. |
| Client/server mismatch | Install the matching client; do not disable the check. |
| Synchronous world / rendering disabled | Coordinate a suitable fresh simulator session. |
| No spawn point / missing vehicle blueprint | Inspect map spawn availability and release blueprints; see `--vehicle` in bridge help. |
| Health endpoint unreachable | Verify the laptop backend, tunnel, and current URL. |
| Authentication rejected | Check the sender token privately; restart bridge after edits. |
| Sender visible but not CARLA ready | Inspect CARLA connection, camera rendering, and bridge logs. |
| Video connecting without frames | Check TURN credentials/expiry, transport, and outbound network access together. |
| Normal video works, TURN-only fails | Direct connectivity works; the relay still needs attention. |
| Tunnel restarted | Update `BACKEND_URL`, restart bridge, and reconnect the dashboard. |

The bridge retries unavailable backend/CARLA connections and brakes locally on failures. A process repeatedly retrying is not a completed setup. If `.env` changes seem ignored, check for shell environment variables overriding them without printing secret values.

## 13. Everyday startup and shutdown

1. Start CARLA as in step 6.
2. Obtain the current tunnel URL and update `carla-service/.env` if it changed.
3. From the GhostDriver project root, start the bridge.

Windows, no activation required:

```powershell
.\carla-service\.venv\Scripts\python.exe carla-service/bridge.py --host 127.0.0.1 --port 2000 --name "Friend CARLA"
```

Linux, no activation required:

```bash
./carla-service/.venv/bin/python carla-service/bridge.py --host 127.0.0.1 --port 2000 --name "Friend CARLA"
```

The laptop owner reconnects, starts video, and resumes controls when ready.

To shut down, have them apply **Emergency stop** and stop video. Press **Control+C** in the bridge terminal before closing CARLA so it can remove its camera and vehicle. Cleanup is best effort if CARLA has already crashed.

## Copyable prompt for the agent on this computer

Copy the entire block below into the agent running on the **friend's GPU computer**. Fill in known nonsecret details or leave them as `UNKNOWN` for inspection. Do not paste the sender token into this prompt.

```text
Set up this computer to run the GhostDriver CARLA simulator and Python sender bridge. Perform installation, configuration, and the verification available here; do not stop at giving a plan or instructions.

Known details (inspect when UNKNOWN):
- OS/version: UNKNOWN
- GPU: UNKNOWN
- Project folder: UNKNOWN
- CARLA installation folder/version: UNKNOWN
- Python versions: UNKNOWN
- Current backend HTTPS tunnel URL: UNKNOWN
- Sender token: enter privately into carla-service/.env, not ordinary chat or reports.

Architecture and scope:
This GPU computer runs CARLA and carla-service/bridge.py. My collaborator's Mac runs React, the Express/Socket.IO backend at 127.0.0.1:4000, and Cloudflare tunnel. Their dashboard normally opens at http://localhost:5173 on their Mac. The bridge connects to their current HTTPS tunnel URL for signaling/status/controls; video uses WebRTC directly or the TURN service configured on their backend.
Do not install Node/npm/cloudflared, run a local GhostDriver backend, or duplicate TURN credentials. Install YOLO through requirements-ai.txt and use the bundled best.pt checkpoint; no research dataset download is needed. Keep CARLA private at 127.0.0.1:2000. Do not expose ports 2000–2002, forward router ports, disable firewalls, or disable authentication.

1. Inspect before changing anything.
Locate the project and follow applicable AGENTS.md instructions. Read README.md, docs/FRIEND_SETUP.md, docs/CONNECTION_TEST.md, carla-service/requirements-ai.txt, carla-service/.env.example, and the bridge's startup/options code.
Identify OS/version, architecture, GPU/driver, free disk space, installed Python interpreters, CARLA release/location, relevant processes, and local port usage. Inspect existing virtual environments and local project changes. Preserve existing files and unrelated simulator work; do not reset the repository or kill unrelated processes.

2. Obtain the project if absent.
Repository: https://github.com/Sujan29k/Ghost_Driver.git
Clone into a suitable user-owned folder only if no existing checkout is available. For private access, request repository access or a project copy instead of inventing credentials. Use the folder containing carla-service as the project root. Do not overwrite local work.

3. Resolve compatibility before installation.
Reuse a suitable installed CARLA release. The Python client must match the simulator version exactly, and its wheel must match OS, architecture, and Python ABI. The interpreter must also support all dependencies in carla-service/requirements-ai.txt.
Do not blindly install the latest Python or carla package. Inspect supplied wheels and official release/package metadata. If CARLA, Python, Git, or necessary runtime prerequisites are absent, consult official documentation, identify the exact compatible downloads and required disk space, and install the necessary components within available permissions. Prefer a compatible packaged simulator to a source build. Respect system/network approval requirements and explain concrete blockers; never bypass approval controls.
pip install carla installs the client, not the simulator. If no compatible combination is available, report the specific conflict and next step rather than concealing a mismatch or weakening checks.

4. Prepare the isolated environment.
Create or reuse carla-service/.venv with the selected interpreter. Preserve an incompatible existing environment rather than silently replacing it. Install requirements-ai.txt and the exact matching CARLA wheel or exact package-index version when supported.
The bridge uses CARLA, aiortc/PyAV, python-socketio, aiohttp, NumPy, python-dotenv, and Ultralytics/PyTorch/OpenCV for YOLO. Treat requirements-ai.txt and its included base requirements as authoritative. Do not install project packages globally or use sudo pip. On Windows, use the venv python.exe directly if activation is blocked; do not relax global execution policy.
Run with the venv interpreter:
python --version
python -m pip check
python -c "import carla, aiortc, av, socketio, aiohttp, numpy, dotenv; print('Bridge imports OK')"
python carla-service/bridge.py --help

5. Start and verify CARLA locally.
Inspect the installed release and use its actual launcher from its installation folder. Common UE4 launchers are .\CarlaUE4.exe on Windows and ./CarlaUE4.sh -RenderOffScreen on Linux. Reuse a suitable running simulator instead of starting a conflicting instance.
Use asynchronous mode with rendering enabled, not no_rendering_mode. Coordinate changes to any other controller's active simulator session.
Run with the project venv:
python -c "import carla; c=carla.Client('127.0.0.1',2000); c.set_timeout(10.0); print('Client:', c.get_client_version()); print('Server:', c.get_server_version()); print('Map:', c.get_world().get_map().name); print('Synchronous:', c.get_world().get_settings().synchronous_mode); print('No rendering:', c.get_world().get_settings().no_rendering_mode)"
Require exact client/server version equality, a map name, Synchronous: False, and No rendering: False. Resolve failures before claiming CARLA is ready.

6. Configure the remote connection privately.
Preserve carla-service/.env if present; otherwise copy its example. Set BACKEND_URL to the current base HTTPS tunnel URL and SENDER_TOKEN through secure local entry.
Do not print .env contents, tokens, TURN credentials, or credential-bearing environment dumps. Do not put secrets in shell arguments, URLs, tracked files, or final reports. Check presence/validity without echoing values, preserve unrelated configuration, and confirm .env is ignored by Git.
Ask for the current nonsecret tunnel URL if missing. For a missing token, ask the local user to enter it directly into carla-service/.env or a secure secret-input facility. Do not request secrets in ordinary chat, substitute a dashboard token, or generate an unmatched random sender token.
Continue independent local setup if connection details are unavailable, then report precisely what remains blocked. Check for stale environment overrides without exposing secret values.

7. Verify reachability and start the bridge.
Request CURRENT_BACKEND_URL/api/health and expect {"success":true}. HTML login/challenge pages are not success. The laptop owner must run their backend and tunnel; do not substitute local services here.
From the project root with the venv interpreter, run:
python carla-service/bridge.py --host 127.0.0.1 --port 2000 --name "Friend CARLA"
Start one bridge instance, retain visible logs/process information, and inspect its behavior. Keep CARLA and the bridge running in persistent terminals supported by your environment for verification. If your session cannot retain them, provide exact launch commands and explicitly say they are stopped.
Use the default 640x360 camera initially. The bridge creates its own vehicle/camera and starts with brakes applied. Do not disable watchdogs, emergency stops, authentication, or version checks. Resolve setup issues within scope; report code defects rather than making unrelated application changes.

8. Coordinate verification with the laptop owner.
Ask the local user to relay status; do not message others automatically. The laptop owner authenticates their dashboard, waits for Friend CARLA and CARLA ready, clicks Connect and Start stream, and confirms actual CARLA scenery, LIVE CARLA VIDEO, and nonzero received FPS.
They then stop video, enable Test TURN only, restart video, and verify actual frames and TURN relay. Afterwards they stop video, disable Test TURN only, and start normally.
Keep controls stopped until both people deliberately begin driving tests. W accelerates, A/D steer, S brakes, and Space/Emergency stop latches the stop. Verify focus-loss/disconnect braking and that reconnecting does not resume controls automatically.
Imports, a healthy HTTP endpoint, a running process, and repository tests do not prove real camera or TURN connectivity. If the other computer is unavailable, finish local setup and mark remote checks pending.

9. Leave a usable handoff.
Report detected OS/GPU, simulator/client/Python versions, installation/project paths, exact venv interpreter, installed prerequisites, and remaining blockers. Redact credentials.
Mark each check passed, failed, or not tested with concise evidence. Distinguish local setup, sender authentication, CARLA camera readiness, received video, TURN-only success, and driving/recovery verification.
Provide exact commands for this computer to start CARLA, edit the tunnel URL, run the bridge from the correct folder, and shut down. State which processes are running and where logs are visible. Persist a short local note with nonsecret paths/commands if useful.
For shutdown, coordinate Emergency stop and Stop stream, stop the bridge with Ctrl+C to clean up its actors, then close CARLA. Do not shut down before the coordinated test finishes unless resolving a failure.
Do not commit secrets, push changes, or claim full success without the corresponding checks.
```
