# Database upgrade and rollback

Use an installation maintenance window with writers stopped. Back up `.env` separately in private storage. Never commit credentials or patient databases.

For an existing local SQLite database, run `python tools/upgrade_database.py --database database/emr.sqlite3`. The tool uses SQLite's backup API, verifies backup integrity, checks the legacy schema, and upgrades to revision `b4e20261015`. It does not use remote credentials or drop existing clinical columns. Keep the resulting backup in private storage and verify application startup before resuming writers.

For a fresh database, use `python -m flask --app run db upgrade`, followed by `python seed.py`. `create_all` does not migrate an existing schema.

Rollback requires stopping writers and restoring a reviewed backup together with its matching application version. Do not copy only the main SQLite file while WAL writers are active. The migration deliberately refuses a destructive downgrade of clinical measurements. Restore drills and MariaDB schema upgrades remain outstanding deployment work.
