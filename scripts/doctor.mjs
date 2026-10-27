import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
let failures = 0;
function check(label, action) {
  try { console.log(`OK   ${label}: ${action()}`); }
  catch (error) { failures++; console.error(`FAIL ${label}: ${error.message}`); }
}
check('Node', () => {
  const [major, minor] = process.versions.node.split('.').map(Number);
  if (major < 22 || (major === 22 && minor < 12)) throw new Error('Use Node 22.12 or newer');
  return process.versions.node;
});
for (const [name, module] of [['Backend dependencies', '../backend/node_modules/express/package.json'],
  ['Frontend dependencies', '../frontend/node_modules/vite/package.json']]) {
  check(name, () => {
    if (!existsSync(new URL(module, import.meta.url))) throw new Error('Run npm run setup');
    return 'installed';
  });
}
check('Backend settings', () => {
  const { parse } = require('../backend/node_modules/dotenv');
  const { loadConfig } = require('../backend/src/config.js');
  const path = new URL('../backend/.env', import.meta.url);
  if (!existsSync(path)) throw new Error('Run npm run configure');
  const env = parse(readFileSync(path));
  const config = loadConfig({ ...env, ...process.env });
  const port = Number(process.env.PORT || env.PORT || 4000);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('PORT must be between 1 and 65535');
  const turn = config.iceServers.some((server) => /^turns?:/.test(server.urls));
  if (!turn) console.log('NOTE TURN is absent. Configure a relay for networks where direct video cannot connect.');
  console.log('NOTE TURN credentials need a live TURN-only video test with your friend.');
  return `distinct tokens; TURN ${turn ? 'configured' : 'absent'}; demo ${config.allowDemo ? 'enabled' : 'disabled'}; port ${port}`;
});
for (const [name, path, expected] of [
  ['YOLO', 'ghostdriver/yolov8n_coco128-5/weights/best.pt', '82441f63220c007b654f201cb55037181e359e85b0bfe6b5ccd55daf0971279e'],
  ['RAFT-Small', 'ghostdriver/models/raft-small.pth', 'c7d41b9cc88442bb8aa911dbb33086dac55a226394b142937ff22d5578717332'],
]) {
  check(`${name} checkpoint`, () => {
    const pathUrl = new URL(`../carla-service/${path}`, import.meta.url);
    if (!existsSync(pathUrl)) throw new Error('Missing checkpoint; copy the integrated carla-service folder');
    const hash = createHash('sha256').update(readFileSync(pathUrl)).digest('hex');
    if (hash !== expected) throw new Error('Checkpoint differs from the bundled sudip-work model (possibly a Git LFS pointer)');
    return 'matches sudip-work 00d414e';
  });
}
console.log('CARLA and GPU checks run on your friend’s computer: python carla-service/check_setup.py --prediction raft');
process.exitCode = failures ? 1 : 0;
