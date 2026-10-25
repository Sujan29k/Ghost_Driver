# First video across two networks

Keep controls stopped during these checks. Both people should be on their normal, different networks.

1. Laptop: configure tokens and ICE settings, run `npm run dev`, open localhost:5173, and authenticate.
2. Laptop: run `cloudflared tunnel --url http://127.0.0.1:4000`. Share the HTTPS address and sender token separately.
3. GPU computer: configure `.env`, start CARLA, activate the matching Python environment, and run `python carla-service/bridge.py`.
4. Laptop: confirm **Sender connected**, then **CARLA ready**. Select **Connect** and **Start stream**.
5. Confirm actual CARLA scenery in **LIVE CARLA VIDEO**, nonzero received FPS, packet-loss readings, and a reported route. CARLA's own camera image is the source. With no received frames, the viewport must show a waiting message, never an animation presented as CARLA.
6. Stop the stream. Select **Test TURN only**, then **Start stream**. Success means actual moving CARLA frames, nonzero FPS, and **TURN relay**. Merely supplying TURN credentials or seeing “video connecting” does not prove TURN works.
7. Stop video and uncheck **Test TURN only** to return to automatic direct-or-relay selection.

The TURN test sets the browser's `iceTransportPolicy` to `relay`, so successful video must traverse TURN. aiortc uses the same TURN credentials but does not expose that browser policy in its public configuration API. This test proves the end-to-end relay path; it does not separately prove every possible sender-side TURN allocation/transport. Route reporting inspects the selected pair's local and remote candidates, so a relay at either end is reported as TURN. If the browser lacks candidate-pair details, it shows **Unknown**, rather than guessing.

Received FPS and packet loss come from browser WebRTC inbound statistics. Loss is measured over the most recent stats interval, with late/reordered packet counter changes clamped at zero. These are receiver measurements, not the configured camera FPS. The dashboard's latency/network-quality indicator is Socket.IO RTT to the **local backend**, not video latency to your friend's GPU computer.

## Recovery and controls, after video works

- Stop/restart the Python bridge. The dashboard should clear video and show no available sender, then rediscover the new sender. Select it and start video again. Controls must stay stopped.
- Interrupt/restart cloudflared (update the sender's URL if using a new Quick Tunnel). Socket.IO reconnects automatically. Select the sender/start video again after discovery returns. Held keys must not survive reconnection.
- Temporarily interrupt the media path while signaling remains connected. Missing decoded frames or a failed peer closes video; up to three video retries use increasing delays. A stalled CARLA camera removes readiness and stops video. After retries are exhausted, use **Start stream** again.
- **Stop stream** cancels video retry intentions. Stopping/disconnecting/locking never resumes controls.
- Only when both people are ready for driving tests: click **Resume controls**, use W/A/S/D, and test Space/**Emergency stop**. Emergency stop latches. Reconnecting, restarting video, or restoring packets must not clear it. The Python local watchdog also latches on a gap in controls; press Resume again if it fired.
- Check focus-loss braking and that closing the dashboard applies brakes. Shutdown cleanup is best effort if the simulator itself has died; verify behavior on the installed CARLA release.

## Troubleshooting

| What you see | What to check |
| --- | --- |
| Backend refuses to start | Two distinct tokens of at least 32 characters; all three TURN values present or all empty. |
| Authentication failed | Correct role token, no whitespace from copying, restart bridge after changing `.env`. Dashboard needs its own token. |
| No vehicle available | Bridge is running; its HTTPS URL is current; cloudflared and local backend are running. From GPU computer, `curl https://YOUR-TUNNEL.trycloudflare.com/api/health` should return only `success: true`. |
| Sender connected but not CARLA ready | CARLA version match, port 2000 locally accessible, async world, fresh rendered camera frames; inspect the sender's CARLA setup log. |
| Video connecting, then timeout | TURN credentials/expiry, endpoint/transport/port, outbound firewall permissions on both networks. A working tunnel only proves signaling. |
| TURN-only fails but normal video works | Direct ICE works, but TURN is not usable. Check service credentials, quotas, relay port ranges and allowed transports with the TURN provider. |
| Video stalls / FPS drops | GPU load, camera rendering, bandwidth; try 640×360. Sender does not send black frames or repeatedly encode a frozen camera as live video. |
| Cloudflare HTML/challenge instead of Socket.IO | Use an endpoint the noninteractive Python client can reach; an Access login/email challenge is not handled by this sender. |
| Quick Tunnel fails to start | Check existing cloudflared config files; follow Cloudflare's Quick Tunnel prerequisites. |
| Controls still stopped after reconnection | Expected. Start received video, release held keys, then deliberately click Resume controls. |

## Validation boundaries

Repository checks cover backend auth and role boundaries, ICE configuration delivery, session isolation, readiness, emergency/reconnect behavior, browser WebRTC decoding with the separately labeled synthetic demo, and the Python command watchdog. An optional Python integration test uses real aiortc and Socket.IO with a stubbed CARLA API to check frame encoding/decoding, camera-loss braking, and cleanup. It does not connect to a simulator. Build and Python syntax checks do not prove CARLA camera compatibility.

Still required on your computers: matching CARLA import and simulator version, actor spawn/cleanup, real RGB frame transmission, Cloudflare reachability from the GPU network, actual direct/relay candidate selection, credentialed TURN-only success, and network-interruption braking. No CARLA simulator or external TURN credentials are supplied with the repository.

References: [selected ICE pair statistics](https://developer.mozilla.org/en-US/docs/Web/API/RTCTransportStats/selectedCandidatePairId), [browser relay policy](https://developer.mozilla.org/en-US/docs/Web/API/RTCIceCandidate/address), [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
