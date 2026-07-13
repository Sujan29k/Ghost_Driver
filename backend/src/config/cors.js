/**
 * CORS configuration.
 * In development we allow all localhost ports since:
 *   - Frontend: http://localhost:5173
 *   - vehicle-sim.html loads Socket.IO script from: http://localhost:4000
 *     and then opens a WebSocket from origin: http://localhost:5173
 */

const isDev = process.env.NODE_ENV !== 'production';

const corsOptions = {
  origin: (origin, callback) => {
    // Allow requests with no origin (e.g. curl, Postman, server-to-server)
    if (!origin) return callback(null, true);

    // In development: allow any localhost port
    if (isDev && /^http:\/\/localhost(:\d+)?$/.test(origin)) {
      return callback(null, true);
    }

    // In production: restrict to FRONTEND_URL env var
    const allowed = process.env.FRONTEND_URL || 'http://localhost:5173';
    if (origin === allowed) return callback(null, true);

    callback(new Error(`CORS: origin "${origin}" is not allowed`));
  },
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization'],
  credentials: true,
};

module.exports = corsOptions;
