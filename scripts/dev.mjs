import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../', import.meta.url));
const children = [];
let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) child.kill('SIGTERM');
  process.exitCode = code;
}
for (const script of ['backend/src/server.js', 'frontend/node_modules/vite/bin/vite.js']) {
  const child = spawn(process.execPath, [fileURLToPath(new URL(`../${script}`, import.meta.url))], {
    cwd: script.startsWith('frontend') ? `${root}/frontend` : root,
    stdio: 'inherit', env: process.env,
  });
  children.push(child);
  child.on('error', (error) => { console.error(error.message); stop(1); });
  child.on('exit', (code) => { if (!stopping) stop(code || 1); });
}
process.on('SIGINT', () => stop());
process.on('SIGTERM', () => stop());
