# Isolated candidate verification

`scripts/verify_candidate.py` checks the deployed image's version, health, readiness, authentication, school timezone, synthetic writes, raw extra credit, transfer history and logout. It accepts only HTTPS Cloud Run URLs for `superteacher-overhaul-staging`; production URLs, traffic-tag URLs for production, redirects, proxies and credentials in URLs are refused. The caller must explicitly pass `--isolated-candidate` after confirming the service uses a separate database and replica prefix. A URL name cannot establish storage isolation by itself.

Use the candidate deployment owner's caller-owned **0600** JSON credential file. Its required field is `password`; optional `url` and `release` must match the command. Do not place the password on the command line. Keep credentials and receipts outside the repository.

```bash
python scripts/verify_candidate.py \
  --isolated-candidate \
  --url 'https://superteacher-overhaul-staging-REPLACE_WITH_ACTUAL_HOST.run.app' \
  --expected-version 'REPLACE_WITH_RELEASE_COMMIT' \
  --credentials /tmp/st-candidate-credentials.json \
  --receipt /tmp/st-candidate-smoke-receipt.json
```

Replace the URL with the exact observed service URL. The script does not deploy, restart, drain, change traffic or initiate a restore. It uses the runtime's existing `httpx` dependency and passcode authentication. Accounts-mode email delivery is outside this smoke.

The script creates a uniquely named synthetic course with an atomic initial section, student, assessment, note and attendance mark. It stores **20.123456789 points out of 10**, then changes the student's name and transfers them to a new empty section. It requires the raw historical score to remain unchanged, active grades to exclude the prior section, notes and attendance to remain, and source/target rosters and scoped overview to reflect the transfer. No records are deleted.

A new private receipt records created IDs after each successful creation, including partial progress if a later operation fails. Existing receipt paths are refused so earlier evidence is preserved. A network interruption after a committed write can leave a record whose response/ID was not received; do not blindly retry to infer whether the original write occurred. A failed/partial receipt is investigation evidence, not a passing durability gate.

After the deployment owner has separately completed the approved isolated restart/restore procedure, read back the same records without creating another dataset:

```bash
python scripts/verify_candidate.py \
  --isolated-candidate \
  --verify-receipt \
  --url 'https://superteacher-overhaul-staging-REPLACE_WITH_ACTUAL_HOST.run.app' \
  --expected-version 'REPLACE_WITH_RELEASE_COMMIT' \
  --credentials /tmp/st-candidate-credentials.json \
  --receipt /tmp/st-candidate-smoke-receipt.json
```

The receipt URL and version must match. This readback still creates and revokes an authentication session; it performs no dataset writes. Both runs must pass before the receipt supports candidate durability. Preserve synthetic history until that gate is reviewed. The script's initial write/readback alone does not prove replica recovery, production safety or a single-writer handoff.
