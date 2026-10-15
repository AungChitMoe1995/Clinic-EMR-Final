"""Template copied to hosted run.py by deploy_to_waifly.py --activate.

Loads the existing hosted environment, upgrades the existing SQLite database on
restart before accepting requests, then serves the staged release. It never seeds
or uploads a local database. Source files for the previous release remain intact.
"""
from pathlib import Path
import json, os, re, subprocess, sys
from datetime import datetime, timezone

RELEASE_NAME = None
BASE = Path(__file__).resolve().parent
if RELEASE_NAME is None or not re.fullmatch(r'emr-[a-f0-9]{7,40}', RELEASE_NAME):
    raise RuntimeError('This bootstrap must be configured by the deployment tool.')
RELEASE = BASE / '.releases' / RELEASE_NAME
STATE_DIR = BASE / '.deploy-backups' / RELEASE_NAME
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Preserve hosted settings. The SFTP client never copies its own .env here.
environment_file = BASE / '.env'
if environment_file.exists():
    for line in environment_file.read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
if os.environ.get('USE_MARIADB', '0') != '0':
    raise RuntimeError('This release bootstrap supports the inspected SQLite installation only.')
if not os.environ.get('SECRET_KEY'):
    raise RuntimeError('A stable hosted SECRET_KEY is required.')
existing_uri = os.environ.get('SQLITE_URL')
if existing_uri:
    raise RuntimeError('An explicit SQLITE_URL needs deployment review before activation.')
database = BASE / 'database' / 'emr.sqlite3'
if not database.is_file():
    raise RuntimeError('The existing hosted database is missing; refusing to create an empty replacement.')
os.environ['SQLITE_URL'] = 'sqlite:///' + database.as_posix()
os.environ['FLASK_ENV'] = 'production'
os.environ['ALLOW_CLINIC_REGISTRATION'] = '0'

result = subprocess.run([sys.executable, str(RELEASE/'tools/upgrade_database.py'), '--database', str(database)],
                        cwd=str(RELEASE), env=os.environ.copy(), capture_output=True, text=True)
if result.returncode:
    (STATE_DIR/'migration-error.log').write_text(result.stdout+'\n'+result.stderr, encoding='utf-8')
    raise RuntimeError('Hosted database upgrade failed. Review the private deployment log and restore the previous startup file.')
(STATE_DIR/'migration.log').write_text(result.stdout+'\n'+result.stderr, encoding='utf-8')
sys.path.insert(0, str(RELEASE))
from app import create_app
app = create_app('production')

@app.after_request
def release_header(response):
    response.headers['X-EMR-Release'] = RELEASE_NAME
    return response

(STATE_DIR/'activation.json').write_text(json.dumps({
    'release': RELEASE_NAME, 'activated_at_utc': datetime.now(timezone.utc).isoformat(),
    'database': 'existing hosted SQLite', 'schema_revision': 'b4e20261015'
}, indent=2), encoding='utf-8')
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=25516, debug=False, threaded=True)
