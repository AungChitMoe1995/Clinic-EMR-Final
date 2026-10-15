# Waifly deployment

The inspected installation runs `run.py` on port 25516 and uses the hosted
`database/emr.sqlite3` in WAL mode. SFTP on port 2022 supports file transfers,
but does not provide remote shell execution. A hosting-panel restart is required.

## Stage and activate

1. Commit the intended release. Configure local SFTP credentials in the ignored
   `.env`, then run `python deploy_to_waifly.py` from an environment with Paramiko.
   This uploads committed application files into `.releases/emr-<revision>` and
   verifies each uploaded file's SHA-256. It does not change the active app.
2. Once a hosting-panel restart is available, run
   `python deploy_to_waifly.py --activate`. This saves the previous startup and
   configuration under `.deploy-backups/emr-<revision>` and atomically replaces
   `run.py` with the release bootstrap. If the SFTP server rejects atomic rename,
   stop and resolve that limitation before restarting.
3. Restart the existing process through the hosting panel. The bootstrap retains
   the hosted environment, requires the existing database, makes a consistent
   SQLite backup using the backup API, applies the additive migration, and only
   then serves the new application. Local environment files and local databases
   are never uploaded. No seed command is run.
4. Check `/login` returns HTTP 200 with the expected `X-EMR-Release` header.
   Inspect the private activation and migration logs under `.deploy-backups`.
   The database backup is under the release's `.local-backups` directory.

Do not treat a copy of only the running SQLite main file as a consistent backup;
committed data may still be in its WAL file.

## Roll back application code

Stop the process through the panel, restore the saved `run.py` from the release's
`.deploy-backups` directory to the root, then start it again. Original root app
sources remain intact. The migration adds columns/tables and does not remove old
ones. Do not overwrite the database to roll back code: restoring a database backup
would discard subsequent records and needs a separate review.

Migration failure prevents the new app from starting; inspect its private error
log and restore the previous startup file. Keep backup directories private.

## Deployment record — 15 October 2026

Release `8fef6f9793fb` was activated at 06:52:30 UTC (13:22:30 MMT).
The hosted database remained `database/emr.sqlite3`. Its verified SQLite backup
is under `.releases/emr-8fef6f9793fb/.local-backups/` on the same server; no local
clinical database was uploaded. Migration logs confirm baseline stamping and
upgrade to `b4e20261015` completed successfully.

This host rejected the POSIX atomic-rename extension. After the normal Stop did
not terminate the old process, the owner explicitly approved Force Stop in the
panel. While offline, the old `run.py` was moved into the private release backup,
and the verified `run.py.pending` was renamed to `run.py` using standard SFTP
rename. The server was then started through the panel.

A read-only request to `/login` returned HTTP 200 with
`X-EMR-Release: emr-8fef6f9793fb`, `X-EMR-Database: sqlite`, and
`Cache-Control: no-store, private`. The login page was also visually inspected.
No automated or authenticated workflow tests were run, as requested.
