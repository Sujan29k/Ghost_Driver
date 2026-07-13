import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // REST API
      '/api': {
        target: 'http://localhost:4000',
        changeOrigin: true,
      },
      // Socket.IO — must proxy BOTH http polling AND ws upgrade
      '/socket.io': {
        target: 'http://localhost:4000',
        ws: true,           // ← critical: enables WebSocket proxying
        changeOrigin: true,
        rewriteWsOrigin: true,
      },
    },
  },
});
