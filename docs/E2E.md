# Browser regression tests

The Playwright suite tests the production Vite build served by FastAPI, including
login and rejection of a wrong passcode, course/section/student onboarding, score
and attendance persistence after reload, reports and offline template drafts,
the unconfigured AI response, sign-out and expired browser-session cleanup,
mobile keyboard focus and Escape dismissal. A correction workflow covers
assignment title/max-point changes while preserving raw scores and recalculating
percentages, student name/grade edits, and private-note creation, editing and
confirmed deletion, all verified after reload. The same workflow moves a student
to another section, checks preserved raw scores in Grade history and an empty
active average, then moves back and verifies the original average is restored. CSV file import covers quoted
commas/escaped quotes, invalid rows, duplicate rows, partial feedback and reload
persistence. Injected HTTP failures verify a failed score write reverts with an
error toast, including restoration of an existing persisted score after a rejected
edit, and a failed roster read recovers through Retry. Every workflow
asserts no uncaught page exceptions or application console errors (expected
401 authentication and injected 503 resource messages are excluded). axe-core checks WCAG A/AA rules on
representative screens and dialogs. Automated checks supplement manual review.

From the repository root, prepare a Python environment and install dependencies:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd web
npm ci
npx playwright install --with-deps chromium
E2E_PYTHON=../.venv/bin/python npm run test:e2e
```

`E2E_PYTHON` selects a Python interpreter with the backend dependencies installed;
it defaults to `python3`. Absolute paths are recommended for existing environments.
`E2E_PORT` selects a dedicated loopback port (default `8765`). The runner refuses
to reuse an existing server. Do not supply a deployment URL: the base URL is
intentionally restricted to the local isolated server. Node must satisfy the
version in `web/package.json`.

Each run creates a temporary SQLite database outside the repository, runs the
real migrations, disables demo seeding, uses the explicit test-only passcode
`superteacher-browser-tests`, generates a temporary signing secret, blanks the AI
key and ignores `.env`. It never connects to the deployment database. FastAPI
binds to `127.0.0.1`. Playwright shuts it down with SIGTERM; the harness disposes
the engine and removes the temporary directory. A forced kill of the process may
leave a `superteacher-e2e-*` directory in the operating system temporary folder.
Tests run in fresh browser contexts with one worker and no persisted auth state.

`npm run test:e2e` builds the app and runs Chromium. `npm run test:e2e:ui` opens
Playwright's interactive runner. For repeat local runs after building, use
`E2E_PYTHON=/absolute/path/to/python npx playwright test`. Type checking includes
the browser tests; Vitest discovers only `src/**/*.test.{ts,tsx}`. Failure traces,
screenshots and the HTML report appear in `web/test-results` and
`web/playwright-report`; treat these as private because they capture page content.

On WSL, installing/building on the Linux filesystem is faster than `/mnt/c`.
Copy the working tree (including uncommitted changes, excluding `node_modules`,
`.venv`, data and test artifacts) to a temporary Linux directory when needed,
then run `npm ci` and the same command there. Remove that copy after verification.

Configuration follows the official [Playwright web server documentation](https://playwright.dev/docs/test-webserver)
and [test configuration documentation](https://playwright.dev/docs/test-configuration).
`reuseExistingServer: false` and graceful shutdown preserve test isolation.
