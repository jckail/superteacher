// Boots the REAL app (uvicorn serving the built web/dist) on a fresh temp SQLite DB.
// usage: node scripts/serve.mjs <port> <seed:true|false>
import { spawn } from 'node:child_process';
import { mkdtempSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const [port, seed] = [process.argv[2], process.argv[3] ?? 'false'];
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
if (!existsSync(join(root, 'web', 'dist', 'index.html'))) {
  console.error('web/dist is missing. Run `npm run build:web` in e2e/ first.');
  process.exit(1);
}
const dir = mkdtempSync(join(tmpdir(), 'st-e2e-'));
const env = {
  ...process.env,
  AUTH_PASSWORD: process.env.E2E_PASSWORD ?? 'e2e-passcode',
  SESSION_SECRET: 'e2e-session-secret-not-for-production',
  DATABASE_URL: `sqlite:///${join(dir, 'e2e.db')}`,
  SEED_DEMO_DATA: seed,
  AUTH_DISABLED: 'false',
  TZ: 'UTC', // match Cloud Run + the browser project (timezoneId UTC); see FINDINGS.md on UTC-vs-local "today"
};
delete env.ANTHROPIC_API_KEY; // the "AI not configured" paths are part of what we test
const py = process.env.E2E_PYTHON ?? 'python';
const child = spawn(py, ['-m', 'uvicorn', 'superteacher.main:app', '--host', '127.0.0.1', '--port', port, '--log-level', 'warning'], {
  cwd: root, env, stdio: 'inherit',
});
const stop = (code = 0) => {
  child.kill('SIGTERM');
  setTimeout(() => { rmSync(dir, { recursive: true, force: true }); process.exit(code); }, 300);
};
['SIGINT', 'SIGTERM'].forEach((s) => process.on(s, () => stop(0)));
child.on('exit', (code) => { rmSync(dir, { recursive: true, force: true }); process.exit(code ?? 0); });
