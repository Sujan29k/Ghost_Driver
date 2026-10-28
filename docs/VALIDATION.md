# Research implementation validation — 2026-10-28

The changes extend the existing application. No production services were restarted and no changes were pushed to GitHub by this implementation session. The sender archive is the handoff for the current working tree.

## Local results

- Backend: `npm test` — **16 tests passed**. Authentication, exclusive ownership, control range/sequence checks, TURN configuration, watchdogs, signaling, reconnect behavior and research acknowledgement safety are covered. New coverage verifies active-mode telemetry does not acknowledge a pending operation and a late acknowledgement cannot undo an emergency stop.
- Python: `python -m unittest discover -s carla-service/tests -v` — **35 Python tests passed** across the full 34-test run and focused reruns after adding the stale-status regression test. Real NumPy/OpenCV/Farneback, buffer timing, irregular frame intervals, no future-frame inputs, reset-during-inference cancellation, raw-image alignment checks, recorder flushing and offline metrics were exercised. CARLA operations in this suite use fixtures.
- Browser: `npm run test:browser` builds the production frontend and runs Chrome. The three existing browser tests passed. The research workflow test covers acknowledgement, forward/reverse, held-key release, comparison settings, autonomy/manual authority in the UI, scenario selection and takeover source. Its final focused run passed after the fixture was corrected to wait for stopped-speed telemetry before changing direction.
- Actual shipped YOLO and RAFT-Small checkpoints loaded and produced output on **CPU**, using `check_setup.py --models-only --prediction raft --device cpu`. The input was a blank synthetic image; this is an inference/compatibility smoke check, not an accuracy result. No CUDA performance claim is made.
- The offline evaluator CLI generated JSON and CSV from a known aligned synthetic pair and correctly reported a worse prediction. See [JSON example](examples/evaluation-example.json) and [CSV example](examples/evaluation-example.csv). These are format examples, not CARLA experiment results.
- Python compilation and `git diff --check` passed. Packaging excludes private `.env` files, datasets and virtual environments.

The Mac validation environment used Python 3.14, NumPy 2.5.4, OpenCV 5.0.0.93, torch 2.14.1 and aiortc 1.15.0. The Windows deployment targets Python 3.10 with the CARLA 0.9.15 Windows x64 client. macOS emitted duplicate FFmpeg/AVFoundation class warnings while loading aiortc/OpenCV together; the checks completed successfully. This does not validate the Windows dependency/driver combination.

## What the mocks establish

The Python bridge integration tests use the real Node backend, Python Socket.IO, aiortc encoding/decoding and local WebRTC transport. CARLA client/world/vehicle/sensor/Traffic Manager APIs are mocked. The research path exercises reverse, verifies the manual loop makes no actuator writes during autonomy, activates a rain scenario during autonomy, observes takeover braking, acknowledges manual control, resets/restores the environment, explicitly resumes autonomy and stops on camera loss. Model inference is stubbed in the transport fixture; separate tests/smoke checks exercise actual models.

Scenario fixtures cover weather/friction restoration, generic collision-obstacle fallback selection, repeated partial/full resets, partial-setup rollback, retained ownership after failed actor destruction, and preservation of unrelated actors. They do not establish collision geometry or real vehicle passability.

The browser research fixture uses synthetic canvas video and simulated sender acknowledgements over the actual backend/WebRTC path. It does not demonstrate CARLA navigation or prediction quality.

## Not tested in a live simulator

CARLA is **not installed in the Mac validation environment**, and the friend's GPU computer was unavailable to this session. Therefore the following require the numbered [two-computer acceptance run](TWO_COMPUTER_TEST.md):

- Actual CARLA 0.9.15 version/client matching, Windows installation and NVIDIA/CUDA throughput.
- Traffic Manager route following in the preserved asynchronous live simulation; CARLA recommends synchronous mode for its most reliable/reproducible TM operation. This release makes no deterministic driving replay claim.
- Actual reverse gear/vehicle physics, obstacle collisions, partial-route recovery, friction response and scenario placement on the chosen map.
- Live safety behavior under delayed/lost cross-network video, operator disconnection, TURN routing and model stalls on the GPU.
- Custom landslide meshes, flood water/depth/force/engine physics, and any learned disaster detector. Stock scenarios are explicitly labeled approximations.
- Repeated operator studies and statistically supported prediction/driving benefits.

The shipped YOLO checkpoint's inspected class list is the 80 COCO categories. It has no dedicated landslide, debris-roadblock, flood-depth or dangerous-rain class. Dataset collection, annotation, session-separated training/test splits, fine-tuning and held-out hazard evaluation remain team work described in [PERSONAL_SETUP_AND_TRAINING.md](PERSONAL_SETUP_AND_TRAINING.md).
