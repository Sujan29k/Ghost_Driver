# Steps to run GhostDriver on both computers

Your Mac runs the website, backend, and tunnel. Your friend's GPU computer runs CARLA and the Python bridge. You can prepare both computers simultaneously, then connect them using your tunnel URL and sender token.

## Setup status recorded on October 25, 2026

The project and Mac were checked when these instructions were prepared:

- Node.js, npm, and `cloudflared` were installed.
- Frontend and backend dependencies were present.
- `backend/.env` contained separate tokens and TURN settings and passed the application's configuration checks.
- The backend was not reachable on port 4000 during that check.
- TURN connectivity and actual CARLA video still needed testing together.

This is a historical setup snapshot, not a live status check. Use the checks below each time you need to confirm the current state.

**Keep your existing `backend/.env`; do not overwrite it with the example file.** This guide contains placeholders only, never actual tokens or passwords.

Your friend's OS and CARLA version were unknown when this guide was written, so Windows and Linux commands are included. Use only the relevant set. Replace example paths and uppercase placeholders with actual values. Commands using your Mac's project path assume the project has not moved.

For subsequent sessions after setup, jump to [step 15](#15-commands-for-later-sessions).

## 1. Understand who does what

| Stage | Your Mac | Friend's GPU computer |
| --- | --- | --- |
| Prepare simultaneously | Check configuration | Get project, prepare Python, install matching CARLA client |
| Start simultaneously | Start backend/dashboard and tunnel | Start CARLA and verify local connection |
| Exchange details | Share current tunnel URL and sender token privately | Save those details in `carla-service/.env` |
| Connect | Authenticate dashboard | Start Python bridge |
| Verify together | Start video, test TURN, then controls | Watch bridge logs and simulator |
| Keep running | Website/backend terminal, tunnel terminal, browser | CARLA and bridge terminal |

```text
YOUR MAC                              FRIEND'S GPU COMPUTER

Browser dashboard                     CARLA simulator
       ↕                                     ↕
Node backend                          Python bridge
       ↕                                     ↕
Cloudflare tunnel ←──── signaling/controls ────┘

Browser dashboard ←── WebRTC video ─── Python bridge
                      direct or TURN
```

Cloudflare carries signaling and controls. WebRTC carries the video.

## 2. Your Mac: check the existing setup

Open Terminal:

```bash
cd /Users/suzankhrl/Desktop/Ghostdriver
node --version
npm --version
cloudflared --version
```

The project requires Node `22.12+`. The version installed during the recorded check met that requirement.

Dependencies were already present. If you later use a fresh project copy or dependencies change, install them with:

```bash
npm run setup
```

Open your existing configuration:

```bash
nano backend/.env
```

Check these settings:

```dotenv
HOST=127.0.0.1
PORT=4000
FRONTEND_URL=http://localhost:5173,http://localhost:4000,http://127.0.0.1:5173,http://127.0.0.1:4000
DASHBOARD_TOKEN=YOUR_EXISTING_DASHBOARD_TOKEN
SENDER_TOKEN=YOUR_EXISTING_SENDER_TOKEN
STUN_URL=stun:stun.l.google.com:19302
TURN_URL=YOUR_EXISTING_TURN_ENDPOINT
TURN_USERNAME=YOUR_EXISTING_TURN_USERNAME
TURN_PASSWORD=YOUR_EXISTING_TURN_PASSWORD
ALLOW_DEMO=false
```

**Those uppercase values are placeholders, not replacement values to paste over your current settings.**

In `nano`, save with **Control+O**, Enter, then exit with **Control+X**.

Remember:

- `DASHBOARD_TOKEN` is for your browser.
- `SENDER_TOKEN` is for your friend's bridge.
- TURN settings must contain actual service credentials; populated fields alone do not prove they work.
- Your friend receives TURN configuration automatically after authentication.
- No frontend `.env` is required with the default ports.
- Keep `.env` files private and out of Git. Do not put tokens in URLs or command arguments.

Only if you intentionally need new tokens, run this twice and save the two different outputs in the appropriate fields:

```bash
openssl rand -hex 32
openssl rand -hex 32
```

Changing tokens requires updating affected clients and restarting the backend.

## 3. Friend: obtain the project while you do step 2

If your friend already has the current project, open its folder and skip cloning.

Otherwise:

```bash
git clone https://github.com/Sujan29k/Ghost_Driver.git
cd Ghost_Driver
```

If the repository is private, your friend needs repository access and GitHub authentication. Alternatively, privately transfer the current project files, excluding `.env` files, `node_modules`, and virtual environments.

Your friend needs the `carla-service` folder but does **not** need to run `npm run setup`.

All friend-side project commands below assume their terminal is inside the folder containing `carla-service`.

## 4. Friend: identify CARLA and Python versions

On Windows PowerShell:

```powershell
py --list
py --version
```

On Linux:

```bash
python3 --version
```

Identify the **CARLA simulator version** from the installed release.

If CARLA is not installed, download and extract the appropriate packaged simulator for the GPU computer. `pip install carla` installs the Python client, not the simulator. The package and client installation process depends on the release; use its matching CARLA installation guide. The [CARLA 0.9.15 guide](https://carla.readthedocs.io/en/0.9.15/start_quickstart/) is a version-specific reference; select documentation matching your actual release.

Three things must agree:

1. CARLA simulator release.
2. CARLA Python client release.
3. Python version and platform supported by that client wheel and this project's dependencies.

For example, a wheel containing `cp310` targets CPython 3.10. Do not choose Python 3.10 solely from this example—inspect the actual wheel.

## 5. Friend: create the Python environment

Use the Python interpreter compatible with the CARLA wheel.

### Windows PowerShell

If the default `py` interpreter is compatible:

```powershell
py -m venv carla-service/.venv
.\carla-service\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r carla-service/requirements.txt
```

If the wheel specifically requires an installed Python 3.10, the environment creation command would instead be:

```powershell
py -3.10 -m venv carla-service/.venv
```

Choose the correct interpreter before creating the environment; the command above is an alternative to the first command, not an additional step.

If PowerShell blocks activation, activation is optional. Use the environment's interpreter directly:

```powershell
.\carla-service\.venv\Scripts\python.exe -m pip install --upgrade pip
.\carla-service\.venv\Scripts\python.exe -m pip install -r carla-service/requirements.txt
```

In that case, replace `python` in every subsequent Windows command with:

```powershell
.\carla-service\.venv\Scripts\python.exe
```

### Linux

If `python3` is compatible:

```bash
python3 -m venv carla-service/.venv
source carla-service/.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r carla-service/requirements.txt
```

If another installed interpreter is required, substitute it in the first command—for example, `python3.10`.

If Ubuntu/Debian reports that `venv` is unavailable for the default system Python:

```bash
sudo apt update
sudo apt install python3-venv
```

Then retry environment creation. A separately installed Python may require its corresponding version-specific venv package.

## 6. Friend: install the matching CARLA Python client

Find the wheel supplied with the CARLA release.

Windows example:

```powershell
Get-ChildItem "C:\CARLA\PythonAPI\carla\dist"
python -m pip install "C:\CARLA\PythonAPI\carla\dist\ACTUAL_MATCHING_WHEEL_FILENAME.whl"
```

Linux example:

```bash
ls "/actual/path/to/CARLA/PythonAPI/carla/dist"
python -m pip install "/actual/path/to/CARLA/PythonAPI/carla/dist/ACTUAL_MATCHING_WHEEL_FILENAME.whl"
```

Alternatively, if the exact simulator release provides a compatible package on the package index:

```bash
python -m pip install "carla==EXACT_SIMULATOR_VERSION"
```

Use **one** installation method.

Check dependencies:

```bash
python -m pip check
python -c "import carla, aiortc, av, socketio, aiohttp, numpy, dotenv; print('Bridge imports OK')"
```

Expected final line:

```text
Bridge imports OK
```

If installation reports an unsupported wheel or no matching distribution, resolve the Python/platform compatibility. Installing a different CARLA client version will not fix the simulator mismatch.

## 7. Your Mac: start the website and backend

In **Mac Terminal 1**:

```bash
cd /Users/suzankhrl/Desktop/Ghostdriver
npm run dev
```

Keep this terminal running. This starts both the backend and frontend.

In another terminal, check the backend:

```bash
curl --fail --show-error http://127.0.0.1:4000/api/health
```

Expected:

```json
{"success":true}
```

Open this address in your browser:

```text
http://localhost:5173
```

Then:

1. Enter your existing `DASHBOARD_TOKEN`.
2. Click **Connect backend**.
3. Leave the page open.

**“No vehicle available” is expected until your friend starts the bridge.**

If ports 4000 or 5173 are already occupied, inspect them:

```bash
lsof -nP -iTCP:4000 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
```

Stop an older GhostDriver instance in its original terminal with **Control+C**, or reuse it.

## 8. Your Mac: start the tunnel and share two details

In **Mac Terminal 2**:

```bash
cloudflared tunnel --url http://127.0.0.1:4000
```

Keep it running.

Copy the actual URL printed by this command, resembling:

```text
https://random-words.trycloudflare.com
```

Quick Tunnel hostnames change when recreated, and the URL stops working when the tunnel process stops. Use the current terminal output rather than an old address from project documentation. See [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).

Send your friend:

1. The current HTTPS tunnel URL.
2. Your `SENDER_TOKEN`, privately and separately.

Your friend does not need your dashboard token or Cloudflare credentials.

Do not add an interactive email/login challenge to this endpoint; the Python sender cannot complete it.

## 9. Friend: start CARLA while you do steps 7–8

Use a separate terminal for the simulator.

For common UE4 CARLA packages:

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

Replace the installation path. If the release uses another executable name, use that release's launcher.

Wait for CARLA to finish loading.

For this bridge:

- Keep CARLA in its default **asynchronous mode**.
- Stop other scripts that enable synchronous mode.
- Keep rendering enabled; `no_rendering_mode` prevents useful RGB camera output.
- Keep simulator ports 2000–2002 private. No router port forwarding is required.

Back in the **GhostDriver project terminal**, with its Python environment active:

```bash
python -c "import carla; c=carla.Client('127.0.0.1',2000); c.set_timeout(10.0); print('Client:', c.get_client_version()); print('Server:', c.get_server_version()); print('Map:', c.get_world().get_map().name); print('Synchronous:', c.get_world().get_settings().synchronous_mode)"
```

Proceed when:

- Client and server versions match exactly.
- A map name prints.
- `Synchronous: False` prints.

A timeout here is a local CARLA problem; fix it before troubleshooting the tunnel.

## 10. Friend: save your connection details

In the GhostDriver project folder:

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

Set:

```dotenv
BACKEND_URL=https://ACTUAL-CURRENT-TUNNEL.trycloudflare.com
SENDER_TOKEN=ACTUAL_SENDER_TOKEN_SHARED_PRIVATELY
```

Use the tunnel's base URL, without `/api/health`, and save the file.

Check reachability from the friend's computer.

Windows PowerShell:

```powershell
Invoke-RestMethod "https://ACTUAL-CURRENT-TUNNEL.trycloudflare.com/api/health"
```

Expected: `success` is `True`.

Linux:

```bash
curl --fail --show-error "https://ACTUAL-CURRENT-TUNNEL.trycloudflare.com/api/health"
```

Expected:

```json
{"success":true}
```

This proves backend reachability. Authentication and video are checked next.

## 11. Friend: start the Python bridge

From the GhostDriver project folder, with the environment active:

```bash
python carla-service/bridge.py --host 127.0.0.1 --port 2000 --name "Friend CARLA"
```

Windows without activation:

```powershell
.\carla-service\.venv\Scripts\python.exe carla-service/bridge.py --host 127.0.0.1 --port 2000 --name "Friend CARLA"
```

Keep the bridge and CARLA running.

The bridge should connect to your backend and CARLA, create a vehicle and a 640×360 RGB camera, and initially keep the brakes applied.

## 12. Your Mac: connect and verify actual video

On your dashboard:

1. Wait for **Friend CARLA** to appear.
2. Wait for **CARLA ready**.
3. Click **Connect** beside that sender.
4. Click **Start stream**.
5. Wait for actual CARLA imagery, **LIVE CARLA VIDEO**, and nonzero received FPS.

Leave controls stopped during this first check.

Then verify TURN:

1. Click **Stop stream**.
2. Check **Test TURN only**.
3. Click **Start stream**.
4. Confirm real video, nonzero FPS, and **TURN relay**.
5. Stop the stream, uncheck **Test TURN only**, and start again for normal operation.

Normal video can work directly even when TURN credentials are invalid. The TURN-only test checks the relay path.

## 13. Both: test driving and recovery

Once video works and your friend is ready to observe:

1. You click **Resume controls**.
2. Keep browser focus on the dashboard, outside text fields.
3. Test brief key presses.

| Key | Action |
| --- | --- |
| `W` | Accelerate |
| `A` | Steer left |
| `D` | Steer right |
| `S` | Brake |
| Space | Emergency stop |

`S` is braking in this implementation, not reverse.

Test the **Emergency stop** button too. Controls should remain stopped until you deliberately resume.

Then verify recovery:

- Switch focus away from the dashboard; your friend checks braking.
- Have your friend stop the bridge with **Control+C**, then restart it.
- Reconnect to the sender and start video again.
- Confirm controls remain stopped until **Resume controls**.
- Test tunnel interruption while your friend observes the simulator. If restarting creates a new URL, update the friend's `.env` and restart the bridge.

## 14. If something fails

| Symptom | Next action |
| --- | --- |
| Backend fails to start | Read Terminal 1; check distinct tokens of at least 32 characters and complete TURN settings. |
| Dashboard authentication fails | Use `DASHBOARD_TOKEN`; restart backend after configuration edits. |
| Friend's health check fails | Check your backend and tunnel are running and the URL is current. |
| Health works but sender authentication fails | Friend's `SENDER_TOKEN` must exactly match yours; restart bridge after edits. |
| Sender appears but CARLA is not ready | Repeat the local CARLA version/map check; inspect bridge logs and rendering mode. |
| Video stays connecting | Check TURN credentials, expiration, endpoint, and outbound network access on both computers. |
| Normal video works but TURN-only fails | Direct connectivity works; the TURN service/configuration still needs fixing. |
| Controls remain stopped | Receive video first, then click **Resume controls**. |
| Video is slow | Keep the default 640×360 size; inspect GPU load and network bandwidth. |

Changing backend TURN settings requires restarting the backend and reconnecting clients. Changing the tunnel URL requires updating your friend's `.env` and restarting the bridge.

## 15. Commands for later sessions

Once setup is complete, these are the regular startup tasks.

### Your Mac

Terminal 1:

```bash
cd /Users/suzankhrl/Desktop/Ghostdriver
npm run dev
```

Terminal 2:

```bash
cloudflared tunnel --url http://127.0.0.1:4000
```

Share the current URL, then open `http://localhost:5173` and authenticate with your dashboard token.

### Friend's GPU computer

Start CARLA as in [step 9](#9-friend-start-carla-while-you-do-steps-78). Update `BACKEND_URL` in `carla-service/.env` if the tunnel URL changed, then run the bridge.

Windows, from their project folder:

```powershell
.\carla-service\.venv\Scripts\python.exe carla-service/bridge.py --host 127.0.0.1 --port 2000 --name "Friend CARLA"
```

Linux, from their project folder:

```bash
source carla-service/.venv/bin/activate
python carla-service/bridge.py --host 127.0.0.1 --port 2000 --name "Friend CARLA"
```

You then select the sender, start video, and resume controls when ready.

### Shutdown

1. On your dashboard, apply **Emergency stop** and stop video.
2. Your friend stops the bridge with **Control+C**, allowing it to clean up its camera and vehicle.
3. Your friend closes CARLA.
4. Stop your tunnel and app terminals with **Control+C**.

## Related project guides

- [Your laptop setup](LAPTOP_SETUP.md)
- [Friend's GPU computer setup](FRIEND_SETUP.md)
- [Two-network verification and troubleshooting](CONNECTION_TEST.md)
- [Repository validation and its limits](VALIDATION.md)
