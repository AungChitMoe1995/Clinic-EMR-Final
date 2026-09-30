# EASY EMR - Database Storage

This directory contains the local SQLite database for EASY EMR:
- **Database File**: `database/emr.sqlite3`
- **Engine Mode**: SQLite with WAL (Write-Ahead Logging) and `synchronous = NORMAL` for high-throughput, non-blocking concurrent reads and writes.
- **Busy Timeout**: 5000 ms to eliminate locking contention.
- **MariaDB Fallback**: Set `USE_MARIADB=1` environment variable if switching back to remote MariaDB (`db.waifly.com:3306`).
