# CARLA + YOLO Python Service

This folder is the designated home for the Python scripts that bridge the CARLA Simulator and YOLO with the Ghost Driver Node.js Backend.

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
