const path = require('node:path');
require('dotenv').config({ path: path.join(__dirname, '../.env'), quiet: true });
const express = require('express');
const http = require('node:http');
const { Server } = require('socket.io');
const cors = require('cors');
const { createVehicleHub } = require('./vehicle-hub');
const { loadConfig, sameToken } = require('./config');

function createServer(options = {}) {
  const config = options.config || loadConfig();
  const app = express();
  const server = http.createServer(app);
  const allowed = (process.env.FRONTEND_URL || 'http://localhost:5173,http://localhost:4000,http://127.0.0.1:5173,http://127.0.0.1:4000').split(',');
  const corsOptions = { origin: (origin, cb) => cb(null, !origin || allowed.includes(origin)), methods: ['GET', 'POST'] };
  app.use(cors(corsOptions));
  const io = new Server(server, { cors: corsOptions, maxHttpBufferSize: 100000 });
  io.use((socket, next) => {
    const { role, token } = socket.handshake.auth || {};
    if (!['dashboard', 'sender'].includes(role) || !sameToken(token, config.tokens[role])) {
      return next(new Error('Authentication failed: check your connection token'));
    }
    socket.data.role = role;
    next();
  });
  const hub = createVehicleHub(io, { ...options, config });
  io.on('connection', hub.register);
  app.get('/api/health', (_req, res) => res.json({ success: true }));
  // Commands require an owned Socket.IO connection. REST must not bypass ownership.
  app.post('/api/control/:action', (_req, res) => res.status(405).json({ success: false, message: 'Use the operator Socket.IO connection' }));
  const dist = path.join(__dirname, '../../frontend/dist');
  app.use(express.static(dist));
  app.get('/', (_req, res) => res.status(503).send('Build the dashboard with npm run build, or use npm run dev and open port 5173.'));
  app.use((_req, res) => res.status(404).json({ success: false, message: 'Not found' }));
  server.on('close', hub.close);
  return { app, server, io, hub, close: () => new Promise((resolve) => { hub.close(); io.close(resolve); }) };
}
if (require.main === module) {
  const instance = createServer();
  const port = Number(process.env.PORT || 4000);
  instance.server.listen(port, process.env.HOST || '127.0.0.1', () => console.log(`GhostDriver backend: http://localhost:${port}`));
  instance.server.on('error', (error) => { console.error(error.message); process.exitCode = 1; instance.hub.close(); });
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => instance.close().then(() => process.exit(0)));
}
module.exports = { createServer };
