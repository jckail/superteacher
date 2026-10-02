#!/bin/sh
# Start the app, with durable SQLite when LITESTREAM_REPLICA_URL is set:
#   1. restore the database from the replica if it is not on disk (no replica yet = first boot = start empty),
#   2. run the app under `litestream replicate -exec`, which streams changes continuously and does a final sync on
#      SIGTERM (Cloud Run's shutdown signal).
# FAIL CLOSED: if the restore fails for any reason other than "there is no replica yet" (permissions, network,
# corrupt replica) we exit non-zero. Starting with an empty database would fork the replica's history and later
# overwrite real data.
set -eu

# Litestream's -exec wants ONE string that it splits itself, so re-quote any argument that needs it (spaces, quotes...).
quote() {
  case "$1" in
    ''|*[!A-Za-z0-9_./:=@%+,-]*) printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")" ;;
    *) printf '%s' "$1" ;;
  esac
}
join_args() {
  out=""
  for a in "$@"; do out="$out $(quote "$a")"; done
  printf '%s' "${out# }"
}

log() { printf '{"severity":"%s","event":"%s","msg":"%s"}\n' "$1" "$2" "$3"; }

if [ -z "${LITESTREAM_REPLICA_URL:-}" ]; then
  log INFO litestream_disabled "LITESTREAM_REPLICA_URL is not set: data is NOT replicated (ephemeral on Cloud Run)"
  exec "$@"
fi

case "$LITESTREAM_REPLICA_URL" in
  gcs://*) log ERROR litestream_config "Litestream's scheme for Cloud Storage is gs://, not gcs://"; exit 78 ;;
esac

case "${DATABASE_URL:-}" in
  sqlite:////*) DB_FILE="${DATABASE_URL#sqlite:///}" ;;
  *) log ERROR litestream_config "LITESTREAM_REPLICA_URL needs DATABASE_URL=sqlite:////absolute/path.db"; exit 78 ;;
esac
export DB_FILE
CONFIG="${LITESTREAM_CONFIG:-/app/litestream.yml}"

log INFO litestream_restore "restoring $DB_FILE if a replica exists"
if ! litestream restore -config "$CONFIG" -if-db-not-exists -if-replica-exists "$DB_FILE"; then
  log ERROR litestream_restore_failed "restore failed: refusing to start with an empty database"
  exit 1
fi

log INFO litestream_replicate "starting replication and the app"
exec litestream replicate -config "$CONFIG" -exec "$(join_args "$@")"
