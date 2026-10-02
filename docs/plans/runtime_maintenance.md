# Python runtime maintenance

Source `c3277b4`, 2026-10-02, updates Python 3.12.7 to 3.12.15 while retaining
Debian Bookworm, the existing requirements and the checksum-pinned Litestream.
The runtime base is pinned to the verified official multi-platform index:

`python:3.12.15-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3`.

Read-only registry metadata independently matched the index, amd64 child and
configuration digests. Application acceptance remains Linux/amd64 because the
existing Litestream installer selects that architecture. The base index does
not establish ARM application compatibility or a publisher signature.
See the [official image manifest](https://raw.githubusercontent.com/docker-library/official-images/master/library/python)
and [Python 3.12.15 release](https://www.python.org/downloads/release/python-31215/).

## Executed acceptance

Independent source reviews passed. Exact-source
[CI37010699744](https://github.com/jckail/superteacher/actions/runs/37010699744)
passed all gates: 1309 API tests without skips/xfails, 194 web tests, four browser
tests and 83 E2E tests. Native API CI used Python 3.12.14; the Docker gate therefore
also checks the actual production image's Python 3.12.15, UID 10001, framework
imports, OpenSSL, SQLite and installed package inventory.

A disposable container reuses that built image and a read-only tests mount.
Its temporary venv inherits production packages, preserves pip and constrains the
pytest installation to the captured production versions. All 40 original visible
distribution versions remained unchanged. The six existing Unicode/security,
account-token, archive-import/viewer and CSV/account-streaming test files passed
259 cases in 31.22 seconds on Python 3.12.15. Dev dependencies are not shipped.
Restricted-directory nonroot startup, health/readiness/static serving, auth and
missing-password refusal also passed.

Protected immutable build `5ebbab7c-acbf-494d-95c3-9926180ff099` succeeded.
Its image digest and final staging/runtime/restore evidence are recorded in
[DEPLOYMENT_STATUS.md](../DEPLOYMENT_STATUS.md). Recovery-only execution
`c3277b4-hlwcb` passed at 13:20:46 UTC, including integrity/FKs/head `0003`, raw
history, final-image Python 3.12.15 and inventory. Staging HTTP and subsequent
receipt readback passed. Both CI and final-image inventories matched all 39
package resolutions observed in the prior release's pip installation log;
that comparison is narrower than a complete prior executed image inventory.

## Remaining maintenance

Python requirement ranges still resolve during each build. The fixed runtime base
does not lock Python packages, the Node build stage, every external build input or
the final image across rebuilds. Preserve final-image inventories and distinguish
package drift from interpreter changes. Existing lockfile/hash and full-image
dependency review work remains open; these checks do not attest absence of
vulnerabilities or reproduce a remote exploit.

The Node build/runtime toolchain alignment and GitHub action/runner updates remain
separate maintenance items. Coordinate one verification owner and use the shared
heavy-check wrapper for expensive WSL checks. Production data mapping, writer
drain, rollback compatibility and domain cutover remain separate release acceptance.
