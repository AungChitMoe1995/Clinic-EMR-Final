"""Stage a committed EMR release without uploading environment files or databases.

--activate replaces the hosted startup file only. The host must then restart the
process. The bootstrap backs up/upgrades the hosted database before serving the
new code. Existing application sources remain available for rollback.
"""
from pathlib import Path, PurePosixPath
import argparse, hashlib, json, os, subprocess
import paramiko
from config import load_dotenv_file
ROOT = Path(__file__).resolve().parent

def mkdirs(sftp, path):
    current = ''
    for part in PurePosixPath(path).parts:
        if part in ('.','..','/'):
            raise ValueError('Only safe relative remote paths are allowed.')
        current = current+'/'+part if current else part
        try:sftp.stat(current)
        except FileNotFoundError:sftp.mkdir(current)

def put_bytes(sftp, remote, data):
    parent = str(PurePosixPath(remote).parent)
    if parent != '.':mkdirs(sftp, parent)
    with sftp.file(remote,'wb') as stream:stream.write(data)
    with sftp.file(remote,'rb') as stream:received=stream.read()
    if hashlib.sha256(received).digest()!=hashlib.sha256(data).digest():
        raise RuntimeError('Uploaded file fingerprint differs: '+remote)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--activate',action='store_true',help='Install startup switch after staging; restart still required')
    args=parser.parse_args()
    load_dotenv_file(str(ROOT/'.env'))
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    release='emr-'+revision[:12]
    files=subprocess.check_output(['git','ls-tree','-r','--name-only',revision],cwd=ROOT,text=True).splitlines()
    selected=[p for p in files if p.startswith(('app/','migrations/')) or p in ['config.py','requirements.txt','tools/upgrade_database.py']]
    if not selected:raise RuntimeError('No application files found in the committed release.')
    host=os.environ['WAIFLY_SFTP_HOST'];port=int(os.environ.get('WAIFLY_SFTP_PORT',2022))
    transport=paramiko.Transport((host,port));transport.banner_timeout=30;transport.auth_timeout=30
    try:
        transport.connect(username=os.environ['WAIFLY_SFTP_USER'],password=os.environ['WAIFLY_SFTP_PASS'])
        sftp=paramiko.SFTPClient.from_transport(transport)
        backup='.deploy-backups/'+release
        mkdirs(sftp,backup)
        for remote in ['run.py','config.py','requirements.txt','.env']:
            destination=backup+'/'+remote
            try:sftp.stat(destination)
            except FileNotFoundError:
                with sftp.file(remote,'rb') as source:contents=source.read()
                put_bytes(sftp,destination,contents)
        manifest={}
        for name in selected:
            if '..' in PurePosixPath(name).parts or name.endswith(('.sqlite3','.db','.pyc')):
                raise RuntimeError('Invalid deployment file: '+name)
            content=subprocess.check_output(['git','show',revision+':'+name],cwd=ROOT)
            put_bytes(sftp,'.releases/'+release+'/'+name,content)
            manifest[name]=hashlib.sha256(content).hexdigest()
        put_bytes(sftp,'.releases/'+release+'/release-manifest.json',json.dumps({'revision':revision,'files':manifest},indent=2).encode())
        print('Staged release:',release,'verified files:',len(manifest))
        if args.activate:
            template=subprocess.check_output(['git','show',revision+':tools/waifly_bootstrap.py'],cwd=ROOT).decode('utf-8')
            startup=template.replace('RELEASE_NAME = None','RELEASE_NAME = '+repr(release),1).encode('utf-8')
            put_bytes(sftp,backup+'/new-run.py',startup)
            temporary='run.py.pending'
            put_bytes(sftp,temporary,startup)
            sftp.posix_rename(temporary,'run.py')
            print('Startup switch installed. Restart the hosted process to upgrade its database and load this release.')
        else:print('Hosted startup, environment and database remain unchanged.')
        sftp.close()
    finally:transport.close()
if __name__=='__main__':main()
