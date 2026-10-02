# SQLite backup and recovery

Run the backup command in the application's Python environment. It takes filesystem paths,
not SQLAlchemy URLs. Create a restricted backup directory owned by the service operator first:

```bash
mkdir -m 700 /secure-backups
python -m superteacher.backup /data/superteacher.db /secure-backups/superteacher-2026-10-01.db
```

Use a unique destination for each run. Exit code `0` means a snapshot was created and passed
SQLite's complete integrity and foreign key checks; exit code `1` means the operation failed.
Messages contain status only, without student records or SQLite diagnostic contents.

The command opens the source read-only and uses SQLite's online backup API, so it can capture
a consistent committed snapshot while the application is running, including databases using
WAL. Copying the live `.db` file alone can lose committed WAL data; use this command instead.
It creates a temporary file in the destination directory, validates it, flushes it, then
atomically publishes the finished snapshot with a hard link. The filesystem must support
hard links. Existing destinations, source aliases (including symlinks and hard links), missing
sources, uninitialized files, and missing destination directories are refused. Publication
also refuses a destination created by a competing process during the backup. A failed run
removes its temporary files; abrupt process termination may leave a hidden
`.superteacher-backup-*` file that an operator can inspect and remove separately.

Snapshots have mode `0600` on filesystems that enforce POSIX permissions. Use a trusted,
private directory and storage with appropriate access controls, encryption, retention, and
off-host replication. On mounted Windows filesystems, verify the directory's Windows ACLs;
POSIX mode bits alone may not restrict access. A backup includes all database records,
including notes and cached AI insights. The command does not back up environment variables,
API keys, or the generated `.session_secret`; handle those separately using the deployment's
secret management. Integrity checks verify SQLite structure and relationships, rather than
the suitability of a backup for a particular application release.

## Rehearse recovery into a new database

Keep the live database and original snapshot untouched. Restore by running the same validated
copy operation with the snapshot as the source and a fresh path as the destination:

```bash
mkdir -m 700 /secure-recovery
python -m superteacher.backup /secure-backups/superteacher-2026-10-01.db /secure-recovery/rehearsal.db
```

Use the matching application release to open this restored database in an isolated instance,
with its own configuration, port, and credentials, and `SEED_DEMO_DATA=false`. For example,
set `DATABASE_URL=sqlite:////secure-recovery/rehearsal.db` for that instance. Application startup
may migrate the restored database; rehearse that using the intended release before cutover.
Confirm course and section counts, roster relationships, grades, attendance, notes, and cached
insights using known reference records. Confirm authentication and a representative read and
write. Keep any rehearsal writes confined to the restored database. Record the snapshot time,
application release, validation outcome, and expected recovery data loss window.

## Production recovery

1. Stop application writers and any replication process. Preserve the current database and
   its SQLite sidecars for investigation; do not overwrite or delete them.
2. Restore a selected snapshot into a **new** database path with the command above. An existing
   production path will be refused. Repeat the isolated rehearsal checks against this file.
3. Configure the application to use the newly restored path, maintain its required ownership
   and access controls, then start the intended release. Verify login, roster, grades,
   attendance, and a representative write. Reconfigure replication to the new path if used.
4. Keep the previous database available for rollback according to retention policy. If
   rollback is needed, stop writers before switching configuration back; account explicitly
   for writes made after the cutover.

Schedule backups according to the acceptable recovery point and rehearse recovery regularly.
A backup stored only on the same volume cannot recover from losing that volume.
