import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const target = env.BACKEND_URL || 'http://127.0.0.1:4000';
  return {
    plugins: [react()],
    server: { host: '127.0.0.1', port: Number(env.WEB_PORT || 5173), strictPort: true, proxy: {
      '/api': { target, changeOrigin: true },
      '/socket.io': { target, ws: true, changeOrigin: true },
    } },
    build: { rollupOptions: { input: { main: resolve(process.cwd(), 'index.html'), vehicle: resolve(process.cwd(), 'vehicle-sim.html') } } },
  };
});
