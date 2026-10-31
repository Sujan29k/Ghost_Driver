# Two-computer startup and research run

**Compatibility update (2026-10-31):** Research startup accepts matching CARLA 0.9.15 or 0.9.16 client/server releases. For 0.9.16 installation and validation steps, follow [CARLA compatibility](CARLA_COMPATIBILITY.md). Earlier 0.9.15 commands below remain valid for that simulator.


These changes must be present on **both** computers. Use the refreshed `artifacts/ghostdriver-sender.zip` for Windows if the working tree has not yet been committed/pushed. A `git pull` alone cannot retrieve unpublished local changes. Preserve each computer's existing `.env` files.

## Mac

From the repository root, install dependencies if needed, then start the dashboard/backend:

```sh
cd ~/Desktop/Ghostdriver
npm ci --prefix backend
npm ci --prefix frontend
npm run dev
```

Open `http://localhost:5173`. Authenticate with the existing dashboard token. In a separate terminal:

```sh
cloudflared tunnel --url http://127.0.0.1:4000
```

Keep both terminals open. Privately send the friend the **new HTTPS URL** printed by Cloudflare and the existing sender token. These are separate fields. Do not send the dashboard token or TURN credentials. For a one-server production-style local run instead of `npm run dev`, use `npm run build` then `npm start` and open `http://localhost:4000`.

## Windows GPU computer

Open PowerShell in the folder containing `carla-service`. For the earlier checkout location:

```powershell
Set-Location "C:\Users\timil\OneDrive\Desktop\hello\Ghost_Driver"
```

If using the ZIP, use its extracted folder instead. Preserve an existing compatible virtual environment. Create one only if needed:

```powershell
py -3.10 -m venv carla-service/.venv
.\carla-service\.venv\Scripts\python.exe -m pip install -r carla-service\requirements-ai.txt
.\carla-service\.venv\Scripts\python.exe -m pip install carla==0.9.15
.\carla-service\.venv\Scripts\python.exe -m pip check
```

Use a CUDA-enabled PyTorch installation appropriate to the installed NVIDIA driver; the [personal setup guide](PERSONAL_SETUP_AND_TRAINING.md) links to the detailed GPU instructions. `pip install carla` supplies the client, not the simulator.

Start the installed CARLA 0.9.15 simulator in another PowerShell terminal. Replace the example install directory with the folder containing `CarlaUE4.exe`:

```powershell
$CarlaInstall = 'C:\CARLA\WindowsNoEditor'
& "$CarlaInstall\CarlaUE4.exe" -windowed -ResX=1280 -ResY=720 -quality-level=Low
```

Wait for the map to load. Keep rendered, asynchronous simulation enabled. Close old sender scripts so only one bridge owns this experiment. Back in the project terminal:

```powershell
.\carla-service\.venv\Scripts\python.exe carla-service\configure.py
.\carla-service\.venv\Scripts\python.exe carla-service\check_setup.py --prediction raft
.\carla-service\.venv\Scripts\python.exe carla-service\bridge.py
```

Enter only the Mac's HTTPS base URL at the backend prompt. Enter the sender token at its separate hidden prompt; Enter retains an already saved token. The setup checker prints/checks client/server versions and actual YOLO class names. The bridge refuses mismatched versions or a research server outside 0.9.15/0.9.16. Keep CARLA and the bridge running.

## Demonstration checklist

1. On the Mac, connect the research vehicle and start video. Confirm `STOPPED`; no motion should begin automatically. Wait for received frames and the comparison's ready state.
2. At rest, choose Reverse, click Take manual control, then press W. Verify backward movement, positive throttle and CARLA gear -1. S brakes. Space latches a stop. Attempt a direction change above the configured low-speed threshold and verify rejection. Release held keys before resuming; choose Forward at rest.
3. Set the straight/left/right route preference while stopped. Start the normal scenario. Start recording with trial label/order and, if desired, raw aligned images. Explicitly start autonomy and verify Traffic Manager drives the ego. Manual keys must not overwrite it.
4. While autonomy runs, start a partial landslide-style scenario, or rain severity 3. Verify the scripted/sensor trigger source, takeover warning, disabled autopilot and fallback braking. Do not interpret a preset selection as learned disaster detection. Stop at a full blockage; do not force a passage.
5. Click Take manual control. Verify acknowledgement before keys work; use reverse at rest if appropriate. Move clear of the hazard. Stop/reset a still-active severe weather scenario. Select Forward at rest and explicitly return to autonomy. Reconnection must never perform this action for you.
6. Stop driving. Try 0/100/200/500/800 ms injection and RAFT/Farneback/Off. Inspect frame IDs and actual timestamp horizon. Compare uses one synchronized composite. The optional reference has transmission delay; prediction is an estimate. Buffer clearing/configuration changes should show buffering, not fresh old imagery.
7. Repeat trials with delayed-only and predicted-only views and the reference hidden. Vary/counterbalance trial order and repeat routes/scenarios; record failed and worse-prediction cases. Stop recording with completed/aborted/blocked outcome.
8. During autonomous and manual operation, test Space, dashboard disconnect, stopping the monitoring video, and camera loss. Verify braking and disabled autopilot. Reconnect/restart video and verify driving remains stopped. Do this in a clear, safe simulated test area.
9. Stop the ego before scenario reset/stop. Verify original weather returns, owned hazards disappear, and no duplicate cameras/ego/safety sensors appear. Ctrl+C the bridge and verify cleanup of application-owned actors without removing unrelated actors.

Live simulator behavior, custom assets, CUDA throughput, route passability and cross-network TURN remain GPU-computer acceptance work. See [PERSONAL_SETUP_AND_TRAINING.md](PERSONAL_SETUP_AND_TRAINING.md) for the complete training/custom environment guide and [VALIDATION.md](VALIDATION.md) for local test evidence.

## Evaluate recordings

On Windows, replace `TRIAL_ID` with an actual subdirectory:

```powershell
.\carla-service\.venv\Scripts\python.exe carla-service\evaluate_trials.py carla-service\recordings\TRIAL_ID --output evaluation.json --csv evaluation.csv
```

Supply multiple trial directories to produce a JSON list and one CSV row per trial. Transfer trial folders manually if analyzing on another machine with NumPy/OpenCV installed.

The report separates `visualReconstruction` (paired MAE/PSNR/SSIM, baseline-only samples, alignment errors and worse-prediction cases) from `taskPerformance` (collisions, lane events, takeover timings and outcomes). Timing uses the sender's monotonic clock. Notification receipt includes signaling round-trip time; it is not the exact time a warning appeared on the Mac. No camera-to-display one-way latency is claimed.
