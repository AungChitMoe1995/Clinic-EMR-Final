"""
Direct deployment script for Waifly container hosting.
Connects via SFTP and synchronizes application files directly to the server.
"""

import os
import sys
import paramiko

# Waifly SFTP Configuration
SFTP_HOST = os.environ.get('WAIFLY_SFTP_HOST', 'node1.waifly.com')
SFTP_PORT = int(os.environ.get('WAIFLY_SFTP_PORT', 2022))
SFTP_USER = os.environ.get('WAIFLY_SFTP_USER', 'warriorking.9d2fb7c6')
SFTP_PASS = os.environ.get('WAIFLY_SFTP_PASS', 'aiXxvKKf@0Y0')

LOCAL_DIR = os.path.abspath(os.path.dirname(__file__))

# Files & directories to sync
SYNC_FILES = [
    'config.py',
    'passenger_wsgi.py',
    'seed.py',
    'requirements.txt',
    'README_WAIFLY.md'
]

SYNC_DIRS = [
    'app',
    'migrations'
]

# Remote run.py template for Waifly (runs on 0.0.0.0:25516 with multi-threading)
REMOTE_RUN_PY = """import os
from app import create_app

app = create_app(os.environ.get('FLASK_ENV', 'development'))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=25516, debug=True, threaded=True)
"""

def ensure_remote_dir(sftp, remote_dir):
    parts = remote_dir.strip('/').split('/')
    path = ''
    for part in parts:
        path = f"{path}/{part}" if path else part
        try:
            sftp.stat(path)
        except IOError:
            try:
                sftp.mkdir(path)
                print(f"Created remote dir: {path}")
            except Exception:
                pass

def upload_file(sftp, local_path, remote_path):
    remote_dir = os.path.dirname(remote_path)
    if remote_dir:
        ensure_remote_dir(sftp, remote_dir)
    sftp.put(local_path, remote_path)
    print(f"  [OK] Uploaded -> {remote_path}")

def deploy():
    print("=" * 60)
    print(f"Deploying to Waifly: {SFTP_HOST}:{SFTP_PORT} as {SFTP_USER}")
    print("=" * 60)

    transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
    try:
        transport.connect(username=SFTP_USER, password=SFTP_PASS)
        sftp = paramiko.SFTPClient.from_transport(transport)
        print("Connected via SFTP successfully!\n")

        # 1. Upload remote run.py with Waifly port 25516
        with sftp.file('run.py', 'w') as f:
            f.write(REMOTE_RUN_PY)
        print("  [OK] Uploaded -> run.py (0.0.0.0:25516 threaded)")

        # 2. Upload root files
        for fname in SYNC_FILES:
            lpath = os.path.join(LOCAL_DIR, fname)
            if os.path.exists(lpath):
                upload_file(sftp, lpath, fname)

        # 3. Upload directories
        for dname in SYNC_DIRS:
            ldir = os.path.join(LOCAL_DIR, dname)
            if not os.path.exists(ldir):
                continue
            for root, dirs, files in os.walk(ldir):
                dirs[:] = [d for d in dirs if d not in ['__pycache__', '.pytest_cache']]
                for file in files:
                    if file.endswith('.pyc') or file.endswith('.pyo'):
                        continue
                    full_local = os.path.join(root, file)
                    rel_path = os.path.relpath(full_local, LOCAL_DIR).replace('\\', '/')
                    upload_file(sftp, full_local, rel_path)

        sftp.close()
        transport.close()
        print("\n" + "=" * 60)
        print("Deployment completed successfully to Waifly!")
        print("Now restart the server in your Waifly Console to apply.")
        print("=" * 60)
    except Exception as e:
        print(f"Deployment failed: {e}")
        if transport.is_active():
            transport.close()
        sys.exit(1)

if __name__ == '__main__':
    deploy()
