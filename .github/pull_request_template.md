## What and why

## How it was verified
<!-- Commands you ran and their results. "Tests exist" is not "tests pass". -->

## Checklist
- [ ] `ruff check . && ruff format --check .` and the focused tests for what changed
- [ ] Schema change? New Alembic revision with a **never-before-used** id (an applied revision id must never be reused or renumbered)
- [ ] New runtime import? It is in `requirements.txt` **and** `requirements.lock` (`scripts/update_lock.sh`)
- [ ] Touches deploy/persistence? Read `docs/DEPLOYMENT.md` and `docs/RELEASE_CHECKPOINT.md` first; no second writer on a replica
- [ ] No secrets, real student data, or personal emails in code, tests, logs or screenshots
