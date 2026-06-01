#!/usr/bin/env bash
# Automated PostgreSQL backup for the AeroVip app.
#
# - Reads DB credentials from the app's .env (DATABASE_URL).
# - Writes a timestamped gzipped pg_dump to $BACKUP_DIR.
# - Keeps the most recent $KEEP backups, deletes older ones.
#
# Run manually:   scripts/backup_db.sh
# Scheduled:      via cron / systemd timer (see scripts/README-backup.md).
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${AEROVIP_BACKUP_DIR:-/home/ubuntu01/backups/aerovip}"
KEEP="${AEROVIP_BACKUP_KEEP:-30}"

# Load DATABASE_URL from .env
set -a
# shellcheck disable=SC1091
. "$APP_DIR/.env"
set +a

# Parse postgresql://user:pass@host:port/dbname
url="${DATABASE_URL#postgresql://}"
creds="${url%%@*}"; rest="${url#*@}"
DBUSER="${creds%%:*}"; DBPASS="${creds#*:}"
hostport="${rest%%/*}"; DBNAME="${rest##*/}"
DBHOST="${hostport%%:*}"; DBPORT="${hostport#*:}"
[ "$DBPORT" = "$DBHOST" ] && DBPORT=5432

mkdir -p "$BACKUP_DIR"
ts="$(date +%Y%m%d-%H%M%S)"
out="$BACKUP_DIR/aerovip-${ts}.sql.gz"
tmp="${out}.partial"

# Dump to a .partial file first, then atomically rename — so a crashed/half dump
# is never mistaken for a good backup.
PGPASSWORD="$DBPASS" pg_dump -h "$DBHOST" -p "$DBPORT" -U "$DBUSER" "$DBNAME" | gzip > "$tmp"
mv "$tmp" "$out"
echo "$(date '+%F %T') backup OK -> $out ($(du -h "$out" | cut -f1))"

# Rotation: keep the newest $KEEP, remove the rest.
ls -1t "$BACKUP_DIR"/aerovip-*.sql.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
    rm -f -- "$old"
    echo "$(date '+%F %T') pruned old backup -> $old"
done
