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
