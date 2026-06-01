# Database backups

## What runs
- **`scripts/backup_db.sh`** — gzipped `pg_dump` of the `aerovip` database.
- Output: `/home/ubuntu01/backups/aerovip/aerovip-YYYYMMDD-HHMMSS.sql.gz`
- Keeps the newest **30** backups (override with `AEROVIP_BACKUP_KEEP`), prunes older.
- Credentials are read from the app's `.env` (`DATABASE_URL`).

## Schedule
Installed in the `ubuntu01` user crontab, daily at 03:00:
```
0 3 * * * /home/ubuntu01/other/aerovip/scripts/backup_db.sh >> /home/ubuntu01/backups/aerovip/backup.log 2>&1
```
Check it: `crontab -l`  ·  Log: `/home/ubuntu01/backups/aerovip/backup.log`

## Run a backup manually
```
/home/ubuntu01/other/aerovip/scripts/backup_db.sh
```

## Restore from a backup
```bash
# pick the file to restore
ls -1t /home/ubuntu01/backups/aerovip/aerovip-*.sql.gz

# restore (overwrites current data in the aerovip DB)
set -a; . /home/ubuntu01/other/aerovip/.env; set +a
url="${DATABASE_URL#postgresql://}"; creds="${url%%@*}"; rest="${url#*@}"
DBUSER="${creds%%:*}"; DBPASS="${creds#*:}"; hostport="${rest%%/*}"; DBNAME="${rest##*/}"
DBHOST="${hostport%%:*}"; DBPORT="${hostport#*:}"; [ "$DBPORT" = "$DBHOST" ] && DBPORT=5432

zcat /home/ubuntu01/backups/aerovip/aerovip-XXXXXXXX-XXXXXX.sql.gz \
  | PGPASSWORD="$DBPASS" psql -h "$DBHOST" -p "$DBPORT" -U "$DBUSER" "$DBNAME"
```
The dump includes `DROP TABLE`/`CREATE TABLE`, so restoring replaces existing tables.
