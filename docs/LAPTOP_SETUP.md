# Your laptop

Your website and Node backend remain local. Only the backend needs a public tunnel address; do not tunnel Vite or CARLA.

## 1. Install and configure

Use Node 22.12 or newer. In the GhostDriver folder:

```sh
npm run setup
cp backend/.env.example backend/.env
```

Generate two different tokens (run this twice):

```sh
openssl rand -hex 32
```

Edit `backend/.env`. Paste one token as `DASHBOARD_TOKEN` and the other as `SENDER_TOKEN`. Keep the dashboard token for yourself. Share the sender token privately with your friend, separately from the public URL. Do not put tokens in shell command arguments, URLs, source files, or `VITE_*` variables.

Example configuration (replace the values marked in angle brackets in your local file):

```dotenv
HOST=127.0.0.1
PORT=4000
FRONTEND_URL=http://localhost:5173,http://localhost:4000,http://127.0.0.1:5173,http://127.0.0.1:4000
DASHBOARD_TOKEN=<your first generated token>
SENDER_TOKEN=<your second generated token>
STUN_URL=stun:stun.l.google.com:19302
TURN_URL=turn:your-turn-server.example:3478?transport=udp
TURN_USERNAME=<external TURN username>
TURN_PASSWORD=<external TURN password>
ALLOW_DEMO=false
```

Obtain a TURN address and credentials from your external TURN service. Use the exact transport and port they supply. For TLS/TCP, an example is `turns:your-turn-server.example:5349?transport=tcp` (some services use port 443). This bridge accepts one STUN and one TURN endpoint, a common subset supported by both browser WebRTC and aiortc. Leave all three TURN values empty for a STUN-only trial, but cross-network connections may then fail. Partial TURN configuration stops backend startup with a configuration error.

The authenticated backend sends these ICE settings to **both** computers. Your friend does not need a second copy of TURN credentials. Restart the backend and reconnect clients after changing them. If the service issues short-lived credentials, renew them before expiry and reconnect; this app does not provision or refresh provider-specific credentials automatically.

`.env` files are ignored by Git. Only `.env.example` templates are intended for source control. No frontend `.env` is needed with the default local ports.

## 2. Start your website and backend

```sh
npm run dev
```

Open **http://localhost:5173**. Enter your dashboard token and click **Connect backend**. Keep this terminal running. The backend listens on loopback port 4000.

Alternatively, serve the built website locally from Express:

```sh
npm run build
npm start
```

Then open **http://localhost:4000**. Use one startup method at a time.

## 3. Start Cloudflare Tunnel

On macOS, install cloudflared if needed:

```sh
brew install cloudflared
```

In another terminal:

```sh
cloudflared tunnel --url http://127.0.0.1:4000
```

Copy the printed `https://...trycloudflare.com` address and send it to your friend. Keep cloudflared running. Quick Tunnel addresses are temporary; after restarting the tunnel, give your friend the new address and have them restart the bridge with the updated `.env`.

Your friend uses this address as `BACKEND_URL`. Your dashboard continues using localhost. You do not need to add the tunnel URL to `FRONTEND_URL`, because your friend uses a Python client rather than a browser origin.

For a persistent hostname, create a named Cloudflare Tunnel and map a public hostname to `http://127.0.0.1:4000`. Its tunnel credentials stay on your laptop. The application's dashboard/sender tokens are separate from Cloudflare credentials. The Python sender expects direct Socket.IO access; an interactive Cloudflare Access login page or email challenge will prevent it connecting.

The tunnel exposes backend HTTP/WebSocket endpoints (and the built dashboard if present); vehicle discovery, ICE credentials, signaling, telemetry, and control events require a valid role token. `/api/health` intentionally returns only `{ "success": true }` for a simple reachability check.

**Keep CARLA ports private.** Do not forward ports 2000–2002, publish them in cloudflared, or ask your friend to open inbound simulator ports. The Python bridge talks to CARLA on their computer. Cloudflare Tunnel carries signaling/status/controls; it does not carry WebRTC video and does not replace TURN.

## 4. Watch video

When your friend starts the bridge, the dashboard lists **Sender connected**, then **CARLA ready** after fresh camera frames and telemetry arrive. Select **Connect**, then **Start stream**. Wait for **LIVE CARLA VIDEO** and a nonzero received FPS. Leave **Resume controls** alone for the first video test.

Continue with [the two-network verification guide](CONNECTION_TEST.md).

Official references: [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/), [named tunnel setup](https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/create-local-tunnel/), [WebRTC connectivity](https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API/Connectivity).
