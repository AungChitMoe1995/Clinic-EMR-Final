"""Back up and upgrade a local SQLite installation, including legacy create_all databases."""
from pathlib import Path
import sys,sqlite3,secrets,argparse
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import create_app
from app.extensions import db
from flask_migrate import stamp,upgrade
from sqlalchemy import inspect

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--database',type=Path,default=ROOT/'database/emr.sqlite3')
    args=parser.parse_args();target=args.database.resolve()
    if not target.exists():raise SystemExit('Database does not exist. Initialize a new installation with flask db upgrade instead.')
    destination=ROOT/'.local-backups';destination.mkdir(exist_ok=True)
    backup=destination/('emr-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
    with sqlite3.connect(target.as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(backup) as copy:
        source.backup(copy)
        if copy.execute('pragma integrity_check').fetchone()[0]!='ok':raise RuntimeError('Backup integrity check failed.')
    app=create_app('production',{'SECRET_KEY':secrets.token_hex(32),'SQLALCHEMY_DATABASE_URI':'sqlite:///'+target.as_posix(),'SQLALCHEMY_ENGINE_OPTIONS':{'connect_args':{'timeout':15}}})
    with app.app_context():
        inspector=inspect(db.engine);tables=set(inspector.get_table_names())
        if 'alembic_version' not in tables:
            missing=[]
            for table in db.metadata.sorted_tables:
                if table.name=='accounts':continue  # Added by the new migration when absent.
                if table.name not in tables:missing.append(table.name);continue
                present={c['name'] for c in inspector.get_columns(table.name)}
                expected={c.name for c in table.columns}-({'version'} if table.name in ['encounters','vouchers','appointments'] else {'height','rbs'} if table.name=='encounter_vitals' else set())
                missing.extend(table.name+'.'+c for c in expected-present)
            if missing:raise RuntimeError('Legacy schema differs from expected baseline: '+', '.join(missing))
            stamp(directory=str(ROOT/'migrations'),revision='3a9f9c9fc63d')
        upgrade(directory=str(ROOT/'migrations'))
        with db.engine.connect() as con:
            if con.exec_driver_sql('pragma foreign_key_check').fetchall():raise RuntimeError('Foreign-key violations require review before clinical use.')
    print('Database upgraded. Local backup:',backup)
if __name__=='__main__':main()
