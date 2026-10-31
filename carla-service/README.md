# CARLA sender

**Compatibility update (2026-10-31):** Research startup accepts matching CARLA 0.9.15 or 0.9.16 client/server releases. For 0.9.16 installation and validation steps, follow [CARLA compatibility](../docs/CARLA_COMPATIBILITY.md). Earlier 0.9.15 commands below remain valid for that simulator.


For the current reverse, autonomy, scenario and comparison workflow, use [the research startup checklist](../docs/TWO_COMPUTER_TEST.md) and [personal setup/training guide](../docs/PERSONAL_SETUP_AND_TRAINING.md). The default research profile accepts matching CARLA 0.9.15 or 0.9.16; `--no-research` retains the legacy single/live-plus-estimate mode.

Use **[the GPU computer setup guide](../docs/FRIEND_SETUP.md)** for installation, matching the CARLA Python client, configuration, and startup commands.

The shorter [Mac + GPU quick start](../docs/QUICK_START.md) includes the transferable
sender archive. After installing dependencies, run `python carla-service/configure.py`
from the project root to save the Mac's tunnel URL and sender token. A new
configuration enables YOLO + RAFT; subsequent runs preserve the saved AI settings.

`bridge.py` is the live CARLA/aiortc sender. `control_state.py` implements its independent braking watchdog. The bridge loads `ghostdriver/yolov8n_coco128-5/weights/best.pt` by default. `perception.py` handles YOLO, `prediction.py` integrates optional RAFT-Small/Farneback prediction, and `traffic.py` owns background actors. See [AI and traffic setup](../docs/AI_TRAFFIC.md). The old `ghostdriver/integration.py` entry point delegates to this bridge; dataset/evaluation scripts remain offline tools.

Use Python 3.10+ and `requirements-ai.txt`. For CARLA 0.9.15 on Windows/Linux x64, Python 3.10 with `carla==0.9.15` is a compatible client choice. Run `python carla-service/check_setup.py --prediction raft` from the repository root after starting CARLA. It checks model inference and simulator compatibility without spawning actors. Add `--models-only` to check models without CARLA.

Local safety checks without CARLA, from a full repository checkout (the sender
archive contains runtime files rather than the test harness):

```sh
python3 -m unittest discover -s carla-service/tests -v
python3 bridge.py --help
```

Run the unittest command from the repository root; run the help command from this folder. Real CARLA camera/spawn/cleanup and cross-network TURN behavior still require the GPU computer and external service credentials.

## Automatic prediction comparison

Record a new research trial with a positive injected video delay (for example 200 ms).
Under **Trial recording**, enable **Save raw aligned images**, start recording,
drive, then stop recording. Samples now include the previous input image as well
as the delayed image and reference target. Two complete sets per second are saved;
the input-pair interval is preserved independently of this sampling rate. Older
recordings without the previous image cannot be replayed by this sweep.

From the repository root on the GPU computer (PowerShell), replace `TRIAL_ID` with
the folder name under `carla-service/recordings`:

```powershell
.\carla-service\.venv312\Scripts\python.exe .\carla-service\benchmark_prediction.py .\carla-service\recordings\TRIAL_ID --output .\prediction-report
```

This runs RAFT once per saved input pair, then tests scales `0.7` and `1.0` with
caps `80`, `160`, and no cap. It also scores the unchanged delayed frame. Read
`prediction-report/report.md` for the ranking, `report.json` for skipped-sample
reasons, and `samples.csv` for individual results. No live driving settings change.
Choose a new output directory on each run. Multiple trial directories may be supplied.
Run offline after driving to avoid competing with the live sender for GPU resources.

Lower MAE and higher SSIM/PSNR are better. Positive gains indicate improvement over
the delayed frame; cap-hit percentage shows whether a limit affected any pixels.
Timing includes flow inference and warping, but excludes scoring and transport.
The ranking is descriptive, not statistical proof: nearby samples are correlated,
and whole-image scores can hide errors around small objects. Confirm the candidate
on separate drives using the same grid before changing defaults. Collect distinct
speed/weather trials and evaluate separately to avoid hiding difficult conditions
inside one average. Use `--scales 0.7 0.85 1 --caps 80 120 160 none` to expand a sweep.
`--method farneback` is available for a lightweight smoke test, not a RAFT benchmark.

## Gentler controls, autonomy and FPS

The dashboard W key now sends 0.5 throttle instead of 1.0, in both forward and
reverse. This halves accelerator input, not the final vehicle speed. S still
applies full braking. Autonomy keeps its independent Traffic Manager speed target.

With research enabled, connect and receive video, then click **Start autonomous
driving** while stopped and in Forward. The sender explicitly configures asynchronous
Traffic Manager operation, releases the stop brake, registers the ego vehicle,
and sets its route. A failed startup disables autopilot and brakes. Start a scenario
while autonomy is running to test takeover. On **TAKEOVER_REQUESTED**, the car brakes;
click **Take manual control** and drive with W/A/S/D. Read **Driving status** or the
sender's mode-change log if it stays stopped. A red light, obstacle, completed route,
active weather threshold, or missing fresh video can still prevent movement.

Video processing no longer constructs unused panels/reference images and reuses
sampling grids. New configurations permit up to 30 AI outputs/second instead of 15;
existing `.env` values still apply. Actual FPS depends on GPU, simulator and transport.
For a lighter RAFT test, run this from the project root on the GPU computer:

```powershell
.\carla-service\.venv312\Scripts\python.exe .\carla-service\bridge.py --prediction raft --ai-fps 30 --raft-iterations 6 --view predicted
```

Predicted-only sends one panel and avoids YOLO annotation work in the research
pipeline. Six RAFT iterations trade possible accuracy for less computation; the
default remains 12. Check the startup log for `RAFT-Small device: cuda:0` and compare
dashboard FPS and prediction compute time against the original configuration.
Use `--view compare` for side-by-side output. Pass the same `--raft-iterations`
value to `benchmark_prediction.py` when evaluating a recording. Neither the FPS
limit nor fewer iterations guarantees a particular received FPS.
