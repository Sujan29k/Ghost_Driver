# CARLA 0.9.16 compatibility

The sender and setup checker now accept matching 0.9.15 or 0.9.16 client/server releases. Mixed versions and unreviewed research releases are rejected. Existing frontend/backend, authentication, WebRTC, model checkpoints, controls and scenario logic are unchanged by this compatibility update.

The [0.9.16 API](https://carla.readthedocs.io/en/0.9.16/python_api/) retains the VehicleControl reverse flag, autopilot enable/disable and Traffic Manager set_path signatures used here. The [official client release](https://pypi.org/project/carla/0.9.16/) includes a Python 3.10 Windows x64 wheel. This establishes API compatibility, not identical physics or live scenario validation.

## Windows steps

Obtain the updated sender files (including carla_compat.py) or refreshed sender ZIP. Stop the old sender and both simulator processes. Keep your existing project environment and private configuration.

From the project root, using the existing Python 3.10 environment:

```powershell
.\carla-service\.venv\Scripts\python.exe -m pip install --upgrade carla==0.9.16
.\carla-service\.venv\Scripts\python.exe -m pip check
```

Launch CarlaUE4.exe specifically from the **0.9.16** installation, in rendered asynchronous mode. Do not run both simulator versions on port 2000. Keep the backend running, then:

```powershell
.\carla-service\.venv\Scripts\python.exe -c "import carla; c=carla.Client('127.0.0.1',2000); c.set_timeout(10); print('Client:',c.get_client_version()); print('Server:',c.get_server_version())"
.\carla-service\.venv\Scripts\python.exe carla-service\check_setup.py --prediction raft
.\carla-service\.venv\Scripts\python.exe carla-service\bridge.py
```

Both printed versions must be 0.9.16. For the all-on-Windows deployment, keep BACKEND_URL=http://127.0.0.1:4000 and use that backend's sender token. For remote operation, retain the current Mac HTTPS backend URL. No token or TURN changes are needed solely for a CARLA version change.

Follow TWO_COMPUTER_TEST.md for reverse, autopilot, takeover, rain/obstruction, camera-loss braking and cleanup acceptance tests; the same checks apply when all processes run on Windows. Assets, routes, physics and GPU throughput must be validated on the installed simulator. No live 0.9.16 simulation was available during this update. Switching simulator versions does not itself retrain YOLO/RAFT or implement realistic flood physics.

Rollback: stop the sender and simulator, install carla==0.9.15 in the same environment, launch the 0.9.15 executable, check both versions, then restart. The updated code still accepts matching 0.9.15.

## Local verification (2026-10-31)

Three version-policy unit tests passed; Python compilation and diff whitespace checks passed. Five transport integration tests, including the newly added 0.9.16 fixture, were skipped because optional transport dependencies were unavailable in the current test environment. The fixture is an API mock, not a real CARLA installation. Live simulator compatibility remains to be verified on the GPU computer.
