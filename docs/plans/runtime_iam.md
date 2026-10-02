# Dedicated runtime identity rehearsal

Updated 2026-10-02. Runtime acceptance remains pending. Current verified staging
release `b5c1b8d` and the public production services keep their existing identities.

The rehearsal uses a new user-managed service account, a dedicated synthetic
Cloud Storage bucket and a project-defined custom role containing exactly
`storage.objects.get`, `storage.objects.create`, `storage.objects.delete` and
`storage.objects.list`. The role is bound only on the new bucket. No project IAM
policy or existing service/bucket policy was changed. Bucket prefixes organize
replicas; the permission boundary is the entire dedicated bucket.

The bucket uses regional standard storage, uniform bucket-level access, enforced
public access prevention and seven-day soft deletion. There is no immutable
retention policy. A separate synthetic canary bucket and enabled secret version
provide known existing targets for denial checks; they contain no real records.
Runtime receives no Secret Manager grant. Operator credentials, resource receipts
and synthetic application credentials remain in restricted local files.

Provisioning succeeded after an initial role-not-found bucket-binding failure.
The operator stopped, verified the exact custom role, and continued the recorded
phase without widening permissions. Runtime role propagation was not inferred
from creation success. The reviewed probe job is now awaiting execution.

Acceptance requires all of the following:

1. Execute the immutable accepted `c3277b4` image under the new identity; verify
   metadata identity, non-root UID and Python version. Exercise create, list,
   read, overwrite and delete on the dedicated bucket. Require HTTP 403 for
   unrelated canary object operations and secret access, with operator existence
   witnesses recorded immediately before the probe. Check seven selected project
   administration permissions; this is not a complete effective IAM audit.
2. Deploy a new, independently named rehearsal service using that same image,
   identity and a verified empty replica prefix. Disable AI/demo data and limit
   instances to one. Verify actual revision, image, identity and environment.
3. Run synthetic authenticated creation, transfer, history, precision and export
   checks. Stop only the owned rehearsal service and inspect application and
   replication lifecycle logs. A successful control-plane deletion does not by
   itself prove final replication or a production writer drain.
4. Restore the replica in an independent read-only job under the same identity
   and image, without starting a server or replica writer. Verify integrity,
   foreign keys, native schema head `0003` and all synthetic receipt records.

Private operator evidence has a durable local checkpoint outside Git. Record
actual outcomes here after each acceptance step. A passing rehearsal will still
require a separate writer-safe staging identity/bucket transition. Production
identity, secret policy, final data authority, writer drain, compatible rollback
and domain cutover remain open.
