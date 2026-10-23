<!-- Title: commit-subject style with the Linear key, e.g. "ci: move CI to Depot CI (JCK-123)". Branch must contain jck-<n>. -->

## Summary
<!-- What changed, in two or three sentences. -->

## Why
<!-- The problem or request this solves. -->
Linear: JCK-

## Changes
<!-- The notable parts. File by file only where that helps a reviewer. -->

## Verification
<!-- Exact commands you ran and their result, plus the Depot CI run link. Say what you could not verify. -->
- [ ] Depot CI `depot-ci / ci-result` green: <!-- https://depot.dev/orgs/f3bqc4vdfr/workflows/... -->

## Risk and rollback
<!-- What could break, who or what it affects, and how to undo it. -->

## Repo checklist
- [ ] `ruff check . && ruff format --check .` and the focused tests for what changed
- [ ] Schema change? New Alembic revision with a **never-before-used** id (an applied revision id must never be reused or renumbered)
- [ ] New runtime import? It is in `requirements.txt` **and** `requirements.lock` (`scripts/update_lock.sh`)
- [ ] Touches deploy/persistence? Read `docs/DEPLOYMENT.md` and `docs/RELEASE_CHECKPOINT.md` first; no second writer on a replica
- [ ] No secrets, real student data, or personal emails in code, tests, logs or screenshots
