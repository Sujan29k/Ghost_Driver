import { randomBytes } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { parse } = require('../backend/node_modules/dotenv');
const { loadConfig } = require('../backend/src/config.js');
const path = fileURLToPath(new URL('../backend/.env', import.meta.url));
let contents = readFileSync(existsSync(path) ? path : new URL('../backend/.env.example', import.meta.url), 'utf8');
const original = existsSync(path) ? contents : null;
const env = parse(contents);
for (const key of ['DASHBOARD_TOKEN', 'SENDER_TOKEN']) {
  if (env[key]) continue;
  const value = randomBytes(32).toString('hex');
  const line = new RegExp(`^\\s*(?:export\\s+)?${key}\\s*=.*$`, 'gm');
  contents = line.test(contents) ? contents.replace(line, `${key}=${value}`) : `${contents.trimEnd()}\n${key}=${value}\n`;
}
try {
  // Validate before writing; existing credentials and TURN settings are preserved.
  loadConfig(parse(contents));
  if (contents !== original) writeFileSync(path, contents, { mode: 0o600 });
  console.log('Backend configuration ready. Existing settings preserved.');
  console.log('Your dashboard token is in backend/.env; share only SENDER_TOKEN with your friend.');
  console.log('Run npm run doctor, then npm run dev. See docs/QUICK_START.md for both computers.');
} catch (error) {
  console.error(`Configuration needs attention: ${error.message}`);
  process.exitCode = 1;
}
