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
