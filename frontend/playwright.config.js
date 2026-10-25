import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests', fullyParallel: false, workers: 1, timeout: 45000,
  use: { baseURL: 'http://127.0.0.1:4100', channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome',
    viewport: { width: 1440, height: 1000 }, trace: 'retain-on-failure' },
  webServer: { command: 'node ../backend/src/server.js', url: 'http://127.0.0.1:4100/api/health',
    reuseExistingServer: false, env: { PORT: '4100', HOST: '127.0.0.1', FRONTEND_URL: 'http://127.0.0.1:4100', DASHBOARD_TOKEN: 'browser-test-dashboard-token-only-0001', SENDER_TOKEN: 'browser-test-sender-token-only-000001', ALLOW_DEMO: 'true', STUN_URL: '', TURN_URL: '', TURN_USERNAME: '', TURN_PASSWORD: '' } },
});
