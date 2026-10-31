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
  await expect(dashboard.getByText('WebRTC RTT', { exact: true })).toBeVisible();
  await expect(dashboard.getByText('Peer round trip', { exact: true })).toBeVisible();
  await expect(dashboard.getByText('Direct', { exact: true }).first()).toBeVisible();
  await expect(dashboard.getByText('Left: live camera · Right: estimated future view (RAFT)')).toBeVisible();
  await dashboard.getByRole('button', { name: 'Resume controls' }).click();
  await expect(dashboard.getByRole('button', { name: 'Resume controls' })).toHaveCount(0);
  await dashboard.locator('video').click();
  await dashboard.bringToFront();
  await dashboard.keyboard.down('w');
  await dashboard.keyboard.down('a');
  await expect(mock.locator('#control')).toContainText('Throttle 0.5 · Brake 0.0 · Steer -0.5');
  await dashboard.keyboard.up('a');
  await expect(mock.locator('#control')).toContainText('Throttle 0.5 · Brake 0.0 · Steer 0.0');
  await expect.poll(async () => parseFloat(await mock.locator('#speed').textContent())).toBeGreaterThan(1);
  await dashboard.keyboard.press('Space');
  await expect(dashboard.getByText('Controls stopped — emergency stop active', { exact: true })).toBeVisible();
  await dashboard.keyboard.up('w');
  await dashboard.keyboard.press('w');
  await expect(mock.locator('#control')).toContainText('Throttle 0.0 · Brake 1.0');
  await dashboard.getByRole('button', { name: 'Resume controls' }).click();
  await expect(dashboard.getByRole('button', { name: 'Resume controls' })).toHaveCount(0);
  await dashboard.keyboard.down('w');
  await expect(mock.locator('#control')).toContainText('Throttle 0.5');
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

test('research UI acknowledges modes, clears held keys, compares views and exposes takeover', async ({ browser }) => {
  const context = await browser.newContext();
  const mock = await context.newPage();
  // Protocol fixture over real Socket.IO/WebRTC. The video remains explicitly
  // synthetic; this test checks browser behavior, never CARLA physics or models.
  let state = { version: 1, commandId: 0, generation: 1, mode: 'STOPPED', stopped: true,
    direction: 'forward', directionLimitKmh: 1, reason: 'Fixture stopped', route: {},
    scenario: { name: 'none' }, policy: {}, trial: {},
    video: { delayMs: 200, method: 'farneback', view: 'compare', reference: false } };
  const parse = message => typeof message === 'string' ? message.match(/^42(\d*)(\[.*)$/s) : null;
  // Socket.IO can register on HTTP polling before it upgrades to WebSocket.
  await mock.route('**/socket.io/**', route => {
    const request = route.request();
    if (request.method() !== 'POST') return route.continue();
    const postData = (request.postData() || '').split('\x1e').map(message => {
      const match = parse(message);
      if (!match) return message;
      const packet = JSON.parse(match[2]);
      if (packet[0] === 'vehicle:join') packet[1] = { name: 'Research protocol fixture', mode: 'carla', researchVersion: 1 };
      return `42${match[1]}${JSON.stringify(packet)}`;
    }).join('\x1e');
    return route.continue({ postData });
  });
  await mock.routeWebSocket(/socket\.io/, connection => {
    const server = connection.connectToServer();
    connection.onMessage(message => {
      const match = parse(message);
      if (match) {
        const packet = JSON.parse(match[2]);
        if (packet[0] === 'vehicle:join') packet[1] = { name: 'Research protocol fixture', mode: 'carla', researchVersion: 1 };
        if (packet[0] === 'vehicle:telemetry') {
          packet[1].research = state;
          packet[1].gear = state.direction === 'reverse' ? '-1' : '1';
          packet[1].comparison = { ...state.video, status: 'ready', predictionReady: state.video.method !== 'off', predictionStatus: 'ready', horizonMs: state.video.delayMs, processingMs: 2 };
          server.send('42["vehicle:status",{"ready":true,"phase":"ready"}]');
        }
        message = `42${match[1]}${JSON.stringify(packet)}`;
      }
      server.send(message);
    });
    server.onMessage(message => {
      const match = parse(message);
      if (match) {
        const [event, data] = JSON.parse(match[2]);
        if (event === 'control:apply') {
          state = { ...state, commandId: data.commandId };
          if (data.emergency) state = { ...state, mode: data.reason === 'Emergency stop' ? 'EMERGENCY_STOP' : 'STOPPED', stopped: true, generation: state.generation + 1 };
        }
        if (event === 'research:apply') {
          state = { ...state, commandId: data.commandId };
          if (data.action === 'mode') state = { ...state, mode: data.data.mode, stopped: data.data.mode === 'STOPPED' };
          if (data.action === 'direction') state = { ...state, direction: data.data.direction };
          if (data.action === 'video') state = { ...state, video: data.data };
          if (data.action === 'scenario') state = { ...state, scenario: { ...data.data, active: true, warnings: ['Fixture flood approximation'], weather: { precipitation: 95 }, friction: .3 } };
          const replyState = structuredClone(state);
          setTimeout(() => server.send(`43${match[1]}${JSON.stringify([{ success: true, state: replyState }])}`), 250);
          if (data.action === 'scenario') setTimeout(() => {
            state = { ...state, mode: 'TAKEOVER_REQUESTED', stopped: true, generation: state.generation + 1,
              takeover: { source: 'scripted', reason: 'Configured fixture hazard', triggerNs: Date.now() * 1e6 } };
          }, 600);
          return;
        }
      }
      connection.send(message);
    });
  });
  try {
    await mock.goto('/vehicle-sim.html');
    await mock.getByLabel('Sender token').fill('browser-test-sender-token-only-000001');
    await mock.getByRole('button', { name: 'Connect demo' }).click();
    const page = await context.newPage();
    await page.goto('/');
    await page.getByLabel('Dashboard token').fill('browser-test-dashboard-token-only-0001');
    await page.getByRole('button', { name: 'Connect backend' }).click();
    await expect(page.getByText('Research protocol fixture', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Connect', exact: true }).click();
    await page.getByRole('button', { name: 'Start stream', exact: true }).click();
    await expect.poll(() => page.locator('video').evaluate(v => v.currentTime)).toBeGreaterThan(.5);
    const panel = page.getByLabel('Research controls');
    await expect(panel).toContainText('Acknowledged: STOPPED');
    await panel.getByRole('button', { name: 'Take manual control', exact: true }).click();
    await expect(panel).toContainText('Pending sender acknowledgement');
    await expect(panel).toContainText('Acknowledged: MANUAL');
    await page.keyboard.down('w');
    await expect(mock.locator('#control')).toContainText('Throttle 0.5');
    await page.keyboard.press('Space');
    await expect(mock.locator('#control')).toContainText('Throttle 0.0 · Brake 1.0');
    await expect.poll(async () => parseFloat(await mock.locator('#speed').textContent())).toBeLessThan(1);
    await expect(panel).toContainText('Acknowledged: EMERGENCY_STOP');
    await expect(page.getByText('Speedometer', { exact: true }).locator('..').getByText('0', { exact: true })).toBeVisible();
    await panel.getByLabel('Drive direction', { exact: true }).selectOption('reverse');
    await expect(panel).toContainText('Direction: reverse');
    await panel.getByRole('button', { name: 'Take manual control', exact: true }).click();
    await expect(panel).toContainText('Acknowledged: MANUAL');
    await page.keyboard.down('w'); // OS repeat from the still-held key must be ignored.
    await page.waitForTimeout(150);
    await expect(mock.locator('#control')).toContainText('Throttle 0.0');
    await page.keyboard.up('w');
    await page.keyboard.down('w');
    await expect(mock.locator('#control')).toContainText('Throttle 0.5');
    await page.keyboard.up('w');
    await page.keyboard.press('Space');
    await expect.poll(async () => parseFloat(await mock.locator('#speed').textContent())).toBeLessThan(1);
    await expect(panel).toContainText('Acknowledged: EMERGENCY_STOP');
    await expect(page.getByText('Speedometer', { exact: true }).locator('..').getByText('0', { exact: true })).toBeVisible();
    await panel.getByLabel('Drive direction', { exact: true }).selectOption('forward');
    await expect(panel).toContainText('Direction: forward');
    await panel.getByLabel('Injected video delay').selectOption('500');
    await panel.getByLabel('Display mode').selectOption('delayed');
    await panel.getByRole('button', { name: 'Apply video settings' }).click();
    await expect(panel).toContainText('Acknowledged: STOPPED');
    await expect(panel.getByLabel('Injected video delay')).toHaveValue('500');
    await panel.getByRole('button', { name: 'Start autonomous driving' }).click();
    await expect(panel).toContainText('Acknowledged: AUTONOMOUS');
    await page.keyboard.down('w');
    await expect(mock.locator('#control')).toContainText('Throttle 0.0');
    await page.keyboard.up('w');
    await panel.getByText('Route and scenarios', { exact: true }).click();
    await panel.getByLabel('Scenario', { exact: true }).selectOption('flood');
    await panel.getByRole('button', { name: 'Start selected scenario', exact: true }).click();
    await expect(panel).toContainText('Acknowledged: TAKEOVER_REQUESTED');
    await expect(panel).toContainText('Configured fixture hazard · Source: scripted');
    await panel.getByRole('button', { name: 'Take manual control', exact: true }).click();
    await expect(panel).toContainText('Acknowledged: MANUAL');
    await page.screenshot({ path: 'test-results/research-dashboard.png', fullPage: true });
  } finally { await context.close(); }
});
