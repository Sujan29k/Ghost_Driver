# Vehicle provider protocol

Transport: Socket.IO v4 protocol (JavaScript socket.io-client 4.x; python-socketio 5.x). WebRTC carries video directly or through TURN. Cloudflare Tunnel carries Socket.IO signaling/status/controls only. All times named `serverTimestamp`/`receivedAt` are server Unix milliseconds; CARLA `simulationTimestamp` is simulation seconds. These clocks must not be subtracted without explicit alignment.

## Authentication and ICE

Both roles authenticate using Socket.IO `auth: {role: "dashboard" | "sender", token}`. Tokens in URLs/query strings are not accepted. The backend requires distinct `DASHBOARD_TOKEN` and `SENDER_TOKEN` values of at least 32 characters. Sender credentials cannot acquire operator ownership; dashboard credentials cannot register a sender. Mock senders additionally require `ALLOW_DEMO=true`.

Authenticated clients request `rtc:config` with `{}` and receive `{success:true, iceServers, allowDemo}`. ICE entries use `{urls, username?, credential?}`. The backend reads STUN_URL, TURN_URL, TURN_USERNAME and TURN_PASSWORD from its environment. Never log these payloads or put credentials in a Vite bundle.

## Discovery and ownership

- Provider → `vehicle:join`: `{name, mode: "mock" | "carla"}`; acknowledgement `{success, vehicleId}`. The current socket ID is the vehicle ID.
- Server → `vehicles:list`: array of `{id, name, mode, busy, ready}`. Emitted on connection and registration/ownership changes. A client can request it with `vehicles:request`.
- Operator → `vehicle:connect`: `{vehicleId}`; acknowledgement `{success, vehicle, emergency}` or `{success:false, message}`. One owner per vehicle; one vehicle per operator.
- Operator → `vehicle:disconnect`: `{}`; acknowledgement `{success:true}`.
- Server → operator `vehicle:released`: `{reason}`. Clear video and driving state.
- Provider sends `vehicle:status` `{ready, controlsStopped}` every 200 ms. CARLA readiness requires fresh camera frames and telemetry. A readiness loss stops video and latches brakes. A locally latched control watchdog is reported back to the owner. Valid status or telemetry must arrive within six seconds. On timeout the server removes registration and releases the operator. If telemetry resumes on an unregistered socket, the server emits `vehicle:registration-required`; the provider repeats `vehicle:join` and resets its command sequence state.

## Controls

Operator → `control:direct`:

```json
{"sequence":1,"throttle":0.5,"brake":0,"steer":-0.25}
```

Send complete state at 20 Hz using volatile emission (do not buffer disconnected driving commands). Sequence is an increasing safe integer per ownership period. Throttle/brake are finite numbers in [0,1]; steer is in [-1,1]. Brake suppresses throttle. Invalid/out-of-order commands and non-owner commands are rejected.

Server → provider `control:apply`:

```json
{"commandId":2,"throttle":0.5,"brake":0,"steer":-0.25,"emergency":false,"serverTimestamp":0,"timeoutMs":750,"reason":"Operator command"}
```

Providers reject older command IDs and use a **local monotonic receipt-time watchdog** to apply brakes after 750 ms without accepted commands. A server timestamp does not prove a command's age across unsynchronized hosts. End-to-end command-age rejection is future work.

Operator `control:emergency` and `control:resume` take `{}` with success acknowledgements. The server broadcasts `vehicle:emergency` `{active}` to the owner and sends braking state to the provider. Controls start latched on each registration/ownership. Resume is accepted only after received video readiness. Stream loss, watchdog timeout, and reconnects keep brakes latched; a new stream never resumes driving. Python also requires a fresh `Controls resumed` command to clear its local latch.

The relay also brakes on stream stop, control timeout, release, and owner disconnect. Providers must brake on backend disconnect themselves.

## Telemetry

Provider → `vehicle:telemetry`:

```json
{"speed":12.3,"throttle":0.5,"brake":0,"steer":0,"heading":90,"gear":"D","frameId":123,"simulationTimestamp":6.15}
```

Speed is km/h; heading is degrees. The five numeric driving fields are required. Frame and simulation time are optional. The server relays sanitized `telemetry:update` only to the owner, adding `vehicleId`, `mode`, `receivedAt`, and authoritative `emergency`. Telemetry is not persisted.

## Video

1. Owner → `stream:request` `{vehicleId, relayOnly?:boolean}` with acknowledgement. CARLA must be ready. Relay-only mode requires configured TURN and forces the browser to use relay candidates.
2. Server → owner `stream:starting` `{sessionId, vehicleId, relayOnly}` and → provider `stream:start` `{sessionId, operatorId, relayOnly}`.
3. Provider → `webrtc:offer` `{sessionId, sdp:{type:"offer", sdp:"..."}}`.
4. Owner → `webrtc:answer` `{sessionId, sdp:{type:"answer", sdp:"..."}}`.
5. Either peer → `webrtc:ice-candidate` `{sessionId, candidate}`. Buffer remote candidates until the corresponding remote SDP is set. The server determines the destination from ownership/session, ignoring arbitrary target IDs.
6. Owner → `stream:ready` `{sessionId}` each second only when new decoded frames arrive. Without first readiness, negotiation expires after 45 seconds. Once ready, five seconds without frame heartbeats stops the stream and latches controls.
7. Owner → `stream:stop` `{}`; either peer may send `stream:error` `{sessionId, message}`. Server → both peers `stream:stopped` `{sessionId, reason}`. Close peer connections and tracks.

A new stream request closes the previous session. Late messages from previous sessions are discarded. For aiortc, send `pc.localDescription` **after** `setLocalDescription`, so SDP contains gathered ICE candidates.

## Web measurements

`ping:measure` `{}` receives an acknowledgement from the server. Compute RTT using the browser's own monotonic start/end timestamps. This is signaling-server RTT only. Video FPS and interval packet loss come from the receiver's WebRTC statistics.

`GET /api/health` exposes only `{success:true}`; it reveals no vehicle or credential details. Legacy unauthenticated REST control endpoints return 405; controls require an owned Socket.IO connection.
