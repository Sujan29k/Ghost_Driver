# GhostDriver personal setup, scenario work, and training guide

## What runs without retraining

Reverse control, stop-at-low-speed direction changes, the timestamped delayed/predicted comparison, mode switching, CARLA Traffic Manager route following, the scripted takeover policy, weather/friction presets, collision-prop roadblocks, flood approximations, and local trial recording use the existing code and shipped checkpoints. CARLA Traffic Manager is simulator autonomy. YOLO detects only the classes in its checkpoint; RAFT estimates image motion. Neither is a trained autonomous-driving or disaster-understanding policy.

The sender currently checks that the CARLA Python client and server match and, for this research profile, requires version **0.9.15**. CARLA 0.9.15 uses CARLA's modified Unreal Engine 4.26 branch for source-built map/asset work. Packaged CARLA installs do not include the Unreal Editor authoring workflow; adding a custom map requires the source/editor build. See the [CARLA 0.9.15 custom map guide](https://carla.readthedocs.io/en/0.9.15/tuto_M_custom_map_overview/) and [UE build notes](https://carla.readthedocs.io/en/0.9.15/build_windows/).

## Mac dashboard and backend

From the project root, install dependencies once and build the frontend:

```sh
npm ci --prefix backend
npm ci --prefix frontend
npm run build --prefix frontend
```

Keep the existing backend and Cloudflare Tunnel configuration. Start the project with `npm run dev` from the root, or use the existing backend/frontend startup arrangement. Do not change the dashboard token, sender token, TURN credentials, or public Tunnel URL to use the research controls; both tokens remain in the existing ignored `.env` files. Keep the backend and Tunnel terminal windows open while the GPU computer connects. Start/restart them only when you are ready to interrupt the current session.

## Friend's Windows GPU computer

1. Pull the project commit or extract `artifacts/ghostdriver-sender.zip` into a folder on the GPU computer. Keep the sender package and CARLA installation separate.
2. In PowerShell, from the sender package root, create/reuse `carla-service/.venv` with a Python version compatible with the installed CARLA wheel. For CARLA 0.9.15 on Windows x64, use Python 3.10 (the release provides a matching wheel):

```powershell
py -3.10 -m venv carla-service/.venv
.\carla-service\.venv\Scripts\python.exe -m pip install -r carla-service\requirements-ai.txt
.\carla-service\.venv\Scripts\python.exe -m pip install carla==0.9.15
.\carla-service\.venv\Scripts\python.exe -m pip check
```

The [official release files](https://pypi.org/project/carla/0.9.15/#files) include CPython 3.10 Windows x64. You can instead install the exact matching local wheel from your CARLA installation; do not install an arbitrary `carla` latest version. See [the detailed friend setup guide](FRIEND_SETUP.md) for wheel selection and prerequisites.
3. Preserve an existing `carla-service/.env`. Only if it is missing, copy `carla-service/.env.example` to `carla-service/.env`. Set `BACKEND_URL` to the current HTTPS `trycloudflare.com` address from your Mac and `SENDER_TOKEN` to the existing backend sender token. Do not paste a token into the URL or commit `.env`.
4. Start CARLA 0.9.15 in windowed/rendered mode. In PowerShell, set `$CarlaInstall` to the installed `WindowsNoEditor` directory, then run `& "$CarlaInstall\CarlaUE4.exe" -windowed -ResX=1280 -ResY=720 -quality-level=Low`. Wait for the map to finish loading. Leave CARLA asynchronous; the live sender refuses a synchronous world because it does not own the simulation tick.
5. In another PowerShell window, from the sender package root run:

```powershell
.\carla-service\.venv\Scripts\python.exe carla-service\configure.py
.\carla-service\.venv\Scripts\python.exe carla-service\check_setup.py --prediction raft
.\carla-service\.venv\Scripts\python.exe carla-service\bridge.py
```

The first command validates the saved GPU profile and can retain the token when prompted. The sender prints and checks the client and server CARLA versions, loads YOLO/RAFT, registers, spawns its ego vehicle and safety sensors, then reports `ready`. If setup fails, use the error in that terminal; the dashboard does not expose private paths or raw exceptions.
The existing package supports `--no-research` for the legacy sender operation. Mode, reverse and scenario controls need the updated backend and sender; the video-comparison pipeline also requires `AI_MODE=yolo`.

## Numbered two-computer acceptance checklist

1. Start the Mac backend and Tunnel; copy the current Tunnel URL. Start CARLA and the updated sender on Windows. Confirm CARLA client/server both report 0.9.15 and the dashboard discovers a ready research vehicle.
2. Connect the dashboard, start video, and leave the car stopped. Confirm mode `STOPPED`, actual gear and direction are shown, then try `R` and the Forward/Reverse selector. The selector should reject while speed is above the configured 1 km/h default. At rest, choose Reverse, then click Take manual control and release/repress any held driving keys; W must reverse, S must brake, A/D steer, and Space must latch a stop. Change to Forward while stopped and verify CARLA's actual gear changes.
3. Select the straight normal scenario, set the route, and explicitly click Start autonomous driving. Confirm the sender acknowledges `AUTONOMOUS`, Traffic Manager drives the ego, and manual W/A/D input does not take authority. Click Take manual control; confirm the mode is acknowledged before keys work.
4. Return to autonomy explicitly, select a partial landslide-style roadblock, and click Start selected scenario while autonomy is running. The hazard is placed ahead of the current position along the route. Confirm the dashboard shows the obstacle approximation or generic parked-vehicle fallback (exact blueprint IDs are in the trial recording), the scripted trigger source, and an obvious takeover warning. Confirm braking occurs while takeover is pending. Select Take manual control and use reverse only after stopping if the partial route requires it. A full blockage should be treated as a stop case.
5. Start with the normal scenario and explicit autonomy. Activate rain severity 3 or the flood approximation while moving and inspect displayed weather, friction, warnings and trigger source. After the weather threshold persists for one second (or the scripted hazard zone is reached), verify the takeover warning and latched brake. Confirm scenario labels never call rain a learned detection and flood warnings list effects that are not implemented. Take manual control to acknowledge the request. To return to autonomy, stop/reset severe weather and move clear of a nearby obstruction/zone, select Forward at rest, then explicitly start autonomy again.
6. Configure Compare with 0, 100, 200, 500 and 800 ms delay. Wait for `ready` at each setting. Check panel source frame IDs and horizon; use delayed-only/predicted-only with the reference hidden for operator trials. Prediction status should say buffering/unavailable if history or model output is missing. Compare panels share one composite WebRTC frame.
7. Start a trial with an order number; drive and trigger takeover; stop the trial and record outcome. On Windows, run `carla-service\.venv\Scripts\python.exe carla-service\evaluate_trials.py carla-service\recordings\<trial-id>`. Check `visualReconstruction` and `taskPerformance` independently. Copy trial folders manually to the Mac if needed.
8. Disconnect the dashboard or stop video during autonomy. Verify the sender disables Traffic Manager and brakes. Reconnect and confirm it stays stopped; require an explicit operator action to resume.
9. Stop/reset the scenario while stopped. Confirm scenario-owned actors disappear and the original weather returns. End the bridge with Ctrl+C and confirm only this application's ego, camera, sensors, traffic and scenario actors are removed.

The Python fixtures and mocked Socket.IO tests do not replace steps on CARLA. The actual CARLA tests must be run on the GPU machine with the installed map, GPU, blueprints and drivers.

## Scenario presets and their limits

`carla-service/scenario-configs/*.json` describe each preset. At runtime the sender records the resolved map and route, spawn and hazard coordinates, seed, weather fields, friction and actors, traffic counts, policy thresholds, expected response, and fallback. The Mac selects the scenario, severity and seed; the hazard is positioned using the active route, not copied map coordinates.

- **Normal:** clear weather, selected lane-following route and existing background traffic.
- **Rain:** configurable severity changes cloud, rain, deposits, wetness, fog and lighting. A stock friction trigger applies a local friction coefficient; appearance and grip are separate recorded effects.
- **Landslide:** available rock/stone/debris collision props are discovered at runtime. If none exist, a stationary four-wheel vehicle is a clearly warned generic roadblock. Partial placement may leave a recovery path; it is not guaranteed passable. Full blockage is a stop experiment.
- **Flood:** puddle/deposit appearance, a low-friction zone and a scripted trigger only. There is no simulated water depth, buoyancy, current, hydroplaning, submerged road mesh or engine flooding.
- **Combined:** rain/friction and an obstruction, with flood-style limitations stated where used.

The sender restores weather and destroys only scenario actors it created. It does not modify the ego vehicle's physics or the map's global settings.

## Custom disaster environments in Unreal Editor

If stock props and approximations are insufficient, create or import a CARLA-compatible map/project using the modified Unreal Engine 4.26 branch used by CARLA 0.9.15. Start from a CARLA example map or the documented custom-map workflow so OpenDRIVE roads, lane markings, map waypoints, spawn points and navigation metadata remain valid. Keep the editor, CARLA source and runtime package on the same CARLA release.

For a landslide asset, create a static mesh with visible rock/debris materials and a simple, closed, non-degenerate collision mesh. Import it into the CARLA content tree, set collision to block vehicle channels, add an Unreal/CARLA blueprint with a stable identifier, place it over the desired road lane, then package/rebuild and test `try_spawn_actor`, collision sensor events (`sensor.other.collision`) and lane passability in the packaged simulator. Create separate partial and fully blocked layouts. Verify object scale in meters and sensor visibility. Do not use a visual-only mesh as evidence of physical obstruction.

For flood physics, create a road/water material and water surface/volume with a defined depth, then implement and validate the vehicle interaction you need: wheel/underbody buoyancy or drag, current force, tire traction changes, sensor visibility/refraction and engine/electrical damage if those claims matter. A water material or particle effect alone does not provide these forces. Record parameters and validate against a stated physical model. Package custom maps/assets with CARLA's map packaging tools and install the same package on each test machine. Until then, use the labeled stock flood approximation.

## Learned hazard models and dataset work

The shipped `best.pt` was inspected locally on 2026-10-28: it exposes the 80 COCO class names (including person, bicycle, car, motorcycle, bus and truck), with no landslide, debris-roadblock, flood-depth or dangerous-rain class. This confirms its class mapping, not its training provenance or accuracy. The dashboard road-object overlay filters to six road-user classes. Repeat the inspection if you replace the checkpoint.

Run `carla-service\.venv\Scripts\python.exe carla-service\check_setup.py --models-only --prediction raft`; it prints the loaded YOLO checkpoint's `names` mapping. Trial manifests also save that mapping, checkpoint hashes and installed package versions. Inspect the mapping and write down its exact classes and training provenance. Do not assume it detects debris, floods or dangerous weather. For each hazard, choose the output task (object detection for discrete debris/vehicles, semantic segmentation for road/water regions, or a separately justified classifier/depth model) and define labels, occlusion rules, severity, and ambiguous examples before annotation.

Collect CARLA sequences for debris, blocked roads, visible water, difficult weather, normal weather, traffic lights, construction and ordinary stops. Record map, route, weather/physics, seed, camera settings, CARLA version and scenario. Split by complete sessions, routes or scenarios before sampling frames; nearby frames from one drive must not leak across training and test. Fine-tune a suitable checkpoint only after the labels and split are fixed. Report per-class precision/recall, false takeover alarms per minute/route, missed hazards, detection/takeover timing and confidence calibration on held-out scenarios. Keep pretrained YOLO, any fine-tuned detector, scripted triggers and simulator-state triggers as separate baselines.

Evaluate RAFT and Farneback separately on held-out sequences with the paired image metrics in the evaluation tool. Inspect difficult occlusion, new-object and camera-motion cases. Fine-tuning is not assumed to solve those limits; image extrapolation cannot reveal content hidden in the delayed observations.

No model training, data upload or paid asset purchase is part of this project change.

## Live timing and repeatability

The existing live application remains asynchronous and never calls `world.tick()`. CARLA documents that Traffic Manager is designed for synchronous simulation and may behave unexpectedly in asynchronous worlds; validate its route following on your GPU before an operator study. See the [0.9.15 Traffic Manager timing guidance](https://carla.readthedocs.io/en/0.9.15/adv_traffic_manager/#synchronous-mode). This release records seeds and resolved configurations but makes no deterministic replay claim. The evaluator is offline image/event analysis, not a synchronous simulator runner. A deterministic driving study would need a separate runner with one tick owner, fixed delta time, synchronized Traffic Manager, and restoration of world/TM settings on exit; do not enable synchronous mode in the live bridge.

For single-view timing benchmarks, delayed-only skips YOLO and prediction; predicted-only runs the selected flow estimator without unused YOLO. Raw image metrics and optional compression run on the bounded recording worker at a maximum of two aligned samples/second. Dropped recording jobs are counted. Recording still consumes CPU/disk resources, so keep recording settings identical across trial conditions and report both inference time and overall processing time.
