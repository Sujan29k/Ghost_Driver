/**
 * Ghost Driver — Backend Server (Phase 1)
 * Node.js + Express + Socket.IO
 */

require('dotenv').config();
const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const cors = require('cors');

const corsOptions = require('./config/cors');
const healthRoutes = require('./routes/health.routes');
const telemetryRoutes = require('./routes/telemetry.routes');
const controlRoutes = require('./routes/control.routes');

const telemetrySocket = require('./sockets/telemetry.socket');
const controlSocket = require('./sockets/control.socket');
const signalingSocket = require('./sockets/signaling.socket');

const PORT = process.env.PORT || 4000;

// ─── Express App ───────────────────────────────────────────────
const app = express();
app.use(cors(corsOptions));
app.use(express.json());

// Routes
app.use('/api/health', healthRoutes);
app.use('/api/telemetry', telemetryRoutes);
app.use('/api/control', controlRoutes);

// 404 fallback
app.use((req, res) => res.status(404).json({ success: false, message: 'Not found' }));

// ─── HTTP + Socket.IO ──────────────────────────────────────────
const server = http.createServer(app);

const io = new Server(server, {
  cors: {
    origin: corsOptions.origin,
    methods: ['GET', 'POST'],
  },
  transports: ['websocket', 'polling'],
});

// Init telemetry broadcaster (subscribes to CARLA simulation)
telemetrySocket.init(io);

io.on('connection', (socket) => {
  console.log(`[Socket] Client connected: ${socket.id}`);

  // Register all socket namespaces on this socket
  telemetrySocket.registerHandlers(socket);
  controlSocket.registerHandlers(socket, io);
  signalingSocket.registerHandlers(socket, io);

  socket.on('disconnect', (reason) => {
    console.log(`[Socket] Client disconnected: ${socket.id} — ${reason}`);
  });
});

// ─── Start ─────────────────────────────────────────────────────
server.listen(PORT, () => {
  console.log(`\n🚗  Ghost Driver Backend running on http://localhost:${PORT}`);
  console.log(`   Health: http://localhost:${PORT}/api/health`);
  console.log(`   ENV:    ${process.env.NODE_ENV || 'development'}\n`);
});

module.exports = { app, server, io };
