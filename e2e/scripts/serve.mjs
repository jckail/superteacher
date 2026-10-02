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
  ANTHROPIC_API_KEY: '', // Explicitly override configuration instead of permitting a .env fallback.
  SCHOOL_TIMEZONE: 'UTC',
  COOKIE_SECURE: 'false',
  ENABLE_DOCS: 'false',
  CORS_ORIGINS: JSON.stringify([`http://127.0.0.1:${port}`]),
  STATIC_DIR: join(root, 'web', 'dist'),
  PYTHONPATH: root,
  TZ: 'UTC', // match Cloud Run + the browser project (timezoneId UTC); see FINDINGS.md on UTC-vs-local "today"
};
delete env.K_SERVICE;
for (const name of Object.keys(env)) if (name.startsWith('LITESTREAM_')) delete env[name];
const py = process.env.E2E_PYTHON ?? 'python';
const executable = py.includes('/') ? resolve(root, py) : py;
const child = spawn(executable, ['-m', 'uvicorn', 'superteacher.main:app', '--host', '127.0.0.1', '--port', port, '--log-level', 'warning'], {
  // The empty temporary working directory prevents Settings from loading the repository's .env.
  cwd: dir, env, stdio: 'inherit',
});
let stopping = false;
let requestedCode = 0;
let killTimer;
const stop = (code = 0) => {
  if (stopping) return;
  stopping = true;
  requestedCode = code;
  child.kill('SIGTERM');
  killTimer = setTimeout(() => child.kill('SIGKILL'), 8_000);
};
['SIGINT', 'SIGTERM'].forEach((s) => process.on(s, () => stop(0)));
child.on('error', (error) => { console.error(`Could not start browser test server: ${error.message}`); requestedCode = 1; });
child.on('close', (code) => {
  clearTimeout(killTimer);
  // Only remove the database after the process and its stdio have closed.
  rmSync(dir, { recursive: true, force: true });
  process.exit(stopping || requestedCode ? requestedCode : (code ?? 1));
});
