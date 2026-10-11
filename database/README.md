# EASY EMR - Database Storage

This directory stores the local SQLite database for EASY EMR:
- **Database File**: `database/emr.sqlite3` (generated automatically via `python seed.py` and excluded from git via `.gitignore`).
- **Engine Mode**: SQLite with WAL (Write-Ahead Logging) and `synchronous = NORMAL` for high-throughput, non-blocking concurrent reads and writes.
- **Busy Timeout**: 5000 ms to prevent locking contention.
- **MySQL / MariaDB Option**: Set `USE_MARIADB=1` in `.env` along with `DB_HOST`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME` to use MySQL/MariaDB instead.
