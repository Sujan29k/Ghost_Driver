# CARLA + YOLO Python Service

This folder is the designated home for the Python scripts that bridge the CARLA Simulator and YOLO with the Ghost Driver Node.js Backend.

## Start the full stack on Windows

From the project root, run `.\start.ps1` in PowerShell or `bash start.sh` in Git Bash. The launcher starts or reuses the Node backend and dashboard, starts CARLA if its RPC port is not already available, then starts the Python gateway. The gateway starts the RAFT worker from `raft-env`.

The gateway uses `carla-service\ghostdriver\.venv` (Python 3.7 for the CARLA 0.9.15 API); RAFT uses the project-level `raft-env` and the bundled `carla-service\ghostdriver\models\raft-small.pth` checkpoint. The checkpoint is stored outside the RAFT Git submodule so it is included when this repository is cloned. The default CARLA installation path is `D:\WindowsNoEditor`. If `CarlaUE4.exe` is elsewhere, set `CARLA_ROOT` to its containing folder before starting:

```powershell
$env:CARLA_ROOT = 'D:\path\to\WindowsNoEditor'
.\start.ps1
```

Use `.\start.ps1 -CheckOnly` to verify the runtime dependencies without starting services. The launcher opens separate terminals for the backend, dashboard, and gateway; keep those windows open while using the app.

## Architecture Integration Guide

To connect the Python scripts to the Operator Dashboard, your Python app needs to connect to the Node.js signaling server using `python-socketio`.

**Node.js Backend URL:** `http://localhost:4000`

### 1. Connection & Discovery
Connect to the Socket.IO server and announce that the vehicle simulator is ready:

```python
import socketio
sio = socketio.Client()
sio.connect('http://localhost:4000')

# Tell the dashboard we exist so the "Connect" button lights up
sio.emit('vehicle:join', {'name': 'CARLA-Sim'})
```

### 2. Pushing Live Telemetry
To make the dashboard speedometer and HUD work, push telemetry data continuously (e.g., at 5 Hz-10 Hz). Right now, the backend simulates this, but once your Python script is ready, you will emit to `telemetry:update` (Note: we will need to update the backend `carla.service.js` to accept this from the socket instead of simulating it, or you can emit a custom event like `vehicle:telemetry` that the backend relays).

### 3. Receiving Controls (WASD)
When the operator presses WASD on the web dashboard, the Node.js server receives it. We will configure the backend to forward these to the Python script so you can apply them to the CARLA vehicle.

```python
@sio.on('control:apply')
def on_control(data):
    throttle = data.get('throttle', 0)
    brake = data.get('brake', 0)
    steer = data.get('steer', 0)
    # vehicle.apply_control(carla.VehicleControl(throttle=throttle, steer=steer, brake=brake))
```

### 4. WebRTC Video Streaming (aiortc)
When the operator clicks "Start Stream" on the dashboard, this exact WebRTC flow happens:

1. Python receives `@sio.on('stream:start')` with `sessionId` and `operatorId`.
2. Python uses `aiortc` to create an `RTCPeerConnection`.
3. Python grabs the CARLA camera frame, wraps it in a `VideoStreamTrack`, and adds it to the peer connection.
4. Python generates an SDP Offer and emits it:
   `sio.emit('webrtc:offer', {'sessionId': sessionId, 'targetId': operatorId, 'sdp': offer.sdp})`
5. Python receives the Dashboard's SDP Answer via `@sio.on('webrtc:answer')`.
6. Python exchanges ICE candidates via `webrtc:ice-candidate`.
7. P2P Video flows!

### YOLO Integration
Once YOLO processes the frames, you can emit bounding boxes or hazard alerts over the socket to render an overlay on the frontend dashboard.
