import { test, expect } from '@playwright/test';

test('mock video, simultaneous controls, stop, resume, late discovery and reconnect', async ({ browser }) => {
  const context = await browser.newContext();
  await context.addInitScript(() => {
    const OriginalPeer = window.RTCPeerConnection;
    window.__testPeers = [];
    window.RTCPeerConnection = class extends OriginalPeer {
      constructor(...args) { super(...args); window.__testPeers.push(this); }
    };
  });
  const errors = [];
  context.on('page', (page) => page.on('pageerror', (error) => errors.push(error.message)));
  const mock = await context.newPage();
  // AI metadata fixture on the explicitly synthetic sender exercises the full
  // relay/store/render path without claiming browser tests perform inference.
  await mock.routeWebSocket(/socket\.io/, (connection) => {
    const server = connection.connectToServer();
    connection.onMessage((message) => {
      if (typeof message === 'string' && message.startsWith('42[')) {
        const packet = JSON.parse(message.slice(2));
        if (packet[0] === 'vehicle:telemetry') {
          packet[1].traffic = { vehicles: 30, bicycles: 5, pedestrians: 20 };
          packet[1].perception = { enabled: true, fresh: true, objects: 3, warning: true,
            inferenceMs: 42, flow: false,
            prediction: { method: 'raft', ready: true, horizonMs: 250, inferenceMs: 20 } };
          message = `42${JSON.stringify(packet)}`;
        }
      }
      server.send(message);
    });
  });
  await mock.goto('http://127.0.0.1:4100/vehicle-sim.html');
  await mock.getByLabel('Sender token').fill('browser-test-sender-token-only-000001');
  await mock.getByRole('button', { name: 'Connect demo' }).click();
  await expect(mock.locator('#status')).toHaveText('Available to dashboard');
  const dashboard = await context.newPage();
  await dashboard.goto('http://127.0.0.1:4100/');
  await dashboard.getByLabel('Dashboard token').fill('browser-test-dashboard-token-only-0001');
  await dashboard.getByRole('button', { name: 'Connect backend' }).click();
  await expect(dashboard.getByText('Demo vehicle', { exact: true })).toBeVisible();
  await dashboard.getByRole('button', { name: 'Connect', exact: true }).click();
  await dashboard.getByRole('button', { name: 'Start stream', exact: true }).click();
  await expect(dashboard.getByText('DEMO VIDEO', { exact: true })).toBeVisible({ timeout: 15000 });
  await expect.poll(() => dashboard.locator('video').evaluate((v) => v.videoWidth)).toBeGreaterThan(0);
  await expect.poll(() => dashboard.locator('video').evaluate((v) => v.currentTime)).toBeGreaterThan(0.5);
  const scene = dashboard.getByLabel('Scene and perception');
  await expect(scene).toContainText('Spawned cars: 30 · Bikes: 5');
  await expect(scene).toContainText('Road objects in frame: 3');
  await expect(scene).toContainText('RAFT · +250 ms estimate');
  await expect(dashboard.getByText('Video RTT', { exact: true })).toBeVisible();
  await expect(dashboard.getByText('Browser ↔ sender', { exact: true })).toBeVisible();
  await expect(dashboard.getByText('Direct', { exact: true }).first()).toBeVisible();
  await expect(dashboard.getByText('Left: live camera · Right: estimated future view (RAFT)')).toBeVisible();
  await dashboard.getByRole('button', { name: 'Resume controls' }).click();
  await expect(dashboard.getByRole('button', { name: 'Resume controls' })).toHaveCount(0);
  await dashboard.locator('video').click();
  await dashboard.bringToFront();
  await dashboard.keyboard.down('w');
  await dashboard.keyboard.down('a');
  await expect(mock.locator('#control')).toContainText('Throttle 1.0 · Brake 0.0 · Steer -0.5');
  await dashboard.keyboard.up('a');
  await expect(mock.locator('#control')).toContainText('Throttle 1.0 · Brake 0.0 · Steer 0.0');
  await expect.poll(async () => parseFloat(await mock.locator('#speed').textContent())).toBeGreaterThan(1);
  await dashboard.keyboard.press('Space');
  await expect(dashboard.getByText('Controls stopped — emergency stop active', { exact: true })).toBeVisible();
  await dashboard.keyboard.up('w');
  await dashboard.keyboard.press('w');
  await expect(mock.locator('#control')).toContainText('Throttle 0.0 · Brake 1.0');
  await dashboard.getByRole('button', { name: 'Resume controls' }).click();
  await expect(dashboard.getByRole('button', { name: 'Resume controls' })).toHaveCount(0);
  await dashboard.keyboard.down('w');
  await expect(mock.locator('#control')).toContainText('Throttle 1.0');
  // Headless Chrome emulates focus for every page; dispatch the lifecycle events explicitly.
  await dashboard.evaluate(() => window.dispatchEvent(new Event('blur')));
  await expect(mock.locator('#control')).toContainText('Throttle 0.0 · Brake 1.0');
  await dashboard.evaluate(() => window.dispatchEvent(new Event('focus')));
  await dashboard.keyboard.up('w');
  // Stop actual outgoing media while signaling stays up: decoded-frame watchdog must retry.
  await mock.evaluate(() => window.__testPeers.at(-1).getSenders().forEach((sender) => sender.track?.stop()));
  await expect(dashboard.getByText('DEMO VIDEO', { exact: true })).toHaveCount(0, { timeout: 10000 });
  await expect(dashboard.getByText('DEMO VIDEO', { exact: true })).toBeVisible({ timeout: 15000 });
  await expect(dashboard.getByRole('button', { name: 'Resume controls' })).toBeVisible();
  await expect(mock.locator('#control')).toContainText('Throttle 0.0 · Brake 1.0');
  await dashboard.getByRole('button', { name: 'Stop stream', exact: true }).click();
  await expect(dashboard.getByText('DEMO VIDEO', { exact: true })).toHaveCount(0);
  await expect(scene).toContainText('YOLO: Inactive');
  await expect(scene).toContainText('Prediction: Off');
  await expect(scene).not.toContainText('Large object in view');
  await expect(mock.locator('#control')).toContainText('Brake 1.0');
  await dashboard.getByRole('button', { name: 'Start stream', exact: true }).click();
  await expect(dashboard.getByText('DEMO VIDEO', { exact: true })).toBeVisible({ timeout: 15000 });
  await dashboard.getByRole('button', { name: 'Disconnect', exact: true }).click();
  await dashboard.getByRole('button', { name: 'Connect', exact: true }).click();
  await dashboard.getByRole('button', { name: 'Start stream', exact: true }).click();
  await expect(dashboard.getByText('DEMO VIDEO', { exact: true })).toBeVisible({ timeout: 15000 });
  await expect(dashboard.getByRole('button', { name: 'Resume controls' })).toBeVisible();
  await dashboard.keyboard.press('w');
  await expect(mock.locator('#control')).toContainText('Throttle 0.0 · Brake 1.0');
  await mock.close();
  await expect(dashboard.getByText('No vehicle available', { exact: true })).toBeVisible();
  await expect(dashboard.getByText('DEMO VIDEO', { exact: true })).toHaveCount(0);
  expect(errors).toEqual([]);
  await context.close();
});


test('dashboard waits without fabricated video and rejects an invalid token', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('Disconnected · Waiting for CARLA video')).toBeVisible();
  await expect(page.locator('video')).toHaveJSProperty('srcObject', null);
  await page.getByLabel('Dashboard token').fill('invalid');
  await page.getByRole('button', { name: 'Connect backend' }).click();
  await expect(page.getByRole('alert')).toContainText('Authentication failed');
  await page.getByLabel('Dashboard token').fill('browser-test-dashboard-token-only-0001');
  await page.getByRole('button', { name: 'Connect backend' }).click();
  await expect(page.getByRole('button', { name: 'Lock dashboard' })).toBeVisible();
  await expect(page.getByText('No vehicle available', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Test TURN only')).toBeDisabled();
  expect(await page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage } })))
    .toEqual({ local: {}, session: {} });
});

test('CARLA startup progress appears before video is available', async ({ page }) => {
  const { io } = await import('socket.io-client');
  const sender = io('http://127.0.0.1:4100', { transports: ['websocket'], forceNew: true,
    auth: { role: 'sender', token: 'browser-test-sender-token-only-000001' } });
  try {
    await new Promise((resolve, reject) => {
      sender.on('connect', resolve); sender.on('connect_error', reject);
    });
    await sender.timeout(3000).emitWithAck('vehicle:join', { name: 'GPU sender test', mode: 'carla' });
    sender.emit('vehicle:status', { ready: false, phase: 'loading-models' });
    await page.goto('/');
    await page.getByLabel('Dashboard token').fill('browser-test-dashboard-token-only-0001');
    await page.getByRole('button', { name: 'Connect backend' }).click();
    await expect(page.getByText('CARLA camera · Loading YOLO and prediction models')).toBeVisible();
    await page.getByRole('button', { name: 'Connect', exact: true }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Loading YOLO and prediction models' })).toBeVisible();
    sender.emit('vehicle:status', { ready: false, phase: 'camera-unavailable' });
    await expect(page.getByRole('status').filter({ hasText: 'Camera or AI frames stopped' })).toBeVisible();
    await expect(page.locator('video')).toHaveJSProperty('srcObject', null);
    sender.emit('vehicle:status', { ready: true, phase: 'ready' });
    await expect(page.getByRole('status').filter({ hasText: /^CARLA ready$/ })).toBeVisible();
    await page.screenshot({ path: 'test-results/dashboard-ready.png', fullPage: true });
  } finally { sender.disconnect(); }
});
