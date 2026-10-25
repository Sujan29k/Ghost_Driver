# Local validation

Checks performed for the remote-video update:

| Check | Result |
| --- | --- |
| `npm test` | 11 backend tests pass: authentication/roles, ICE configuration, ownership, session isolation, readiness, lost-frame heartbeat, control watchdog and latched stops. |
| `npm run test:browser` | 2 Chrome tests pass: authenticated demo WebRTC playback, real outgoing-track interruption and automatic video recovery, no automatic control resume, driving/emergency stop, invalid token, waiting screen, no token persistence. Includes a production Vite build. |
| Python unittest with requirements installed | 4 tests pass: 3 local control-state tests plus 1 aiortc/Socket.IO integration using a CARLA API stub. The integration decodes BGRA-derived test frames, checks camera-loss braking, and verifies actor cleanup. |
| Python syntax and `bridge.py --help` | Pass. Help works without CARLA or video dependencies installed. |

Python integration dependencies were installed in a temporary virtual environment. Tested versions include Python 3.14, aiortc 1.15.0, python-socketio 5.17.0, aiohttp 3.14.4, NumPy 2.5.3 and PyAV 17.1.0. **This is not a recommendation to use Python 3.14 for CARLA**: your friend's Python version must support their matching CARLA wheel and the bridge dependencies. The requirements allow compatible versions rather than pinning the laptop's environment.

No CARLA installation, public Cloudflare tunnel, external TURN account, or second network was used. The test camera is a fixture confined to the test suite; it is not a fallback in the application. Real CARLA camera behavior and version compatibility, internet reachability, actual TURN allocation/relay, and cross-network failure behavior remain to be verified using [CONNECTION_TEST.md](CONNECTION_TEST.md).
