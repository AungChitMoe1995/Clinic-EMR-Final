import pytest
from app import create_app
from app.extensions import db as _db
from app.models import User, Doctor, RegistrationNumberSetting, SirNameSetting, PatientFieldSetting, SystemSetting

@pytest.fixture(scope='session')
def app():
    app = create_app('testing')
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()

@pytest.fixture(scope='function')
def db(app):
    with app.app_context():
        _db.create_all()

        # Seed minimal settings
        if not RegistrationNumberSetting.query.first():
            _db.session.add(RegistrationNumberSetting(
                format_pattern='REG-{YYYY}-{NUMBER}',
                increment_amount=1,
                next_number=101,
                padding=6
            ))

        if not SirNameSetting.query.first():
            for title, g in [('U', 'Male'), ('Daw', 'Female'), ('Ko', 'Male'), ('Ma', 'Female'), ('Dr', 'Male')]:
                _db.session.add(SirNameSetting(title=title, default_gender=g, is_default=True, display_order=1))

        if not PatientFieldSetting.query.first():
            for fn, req in [('sir_name', True), ('patient_name', True), ('gender', True), ('phone_number', True)]:
                _db.session.add(PatientFieldSetting(field_name=fn, label=fn.replace('_', ' ').title(), is_required=req, is_visible=True))

        if not SystemSetting.query.first():
            _db.session.add(SystemSetting(setting_key='default_state_region', setting_value='Yangon'))

        _db.session.commit()
        yield _db
        _db.session.rollback()
        # Clean data between test runs
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()

@pytest.fixture
def client(app, db):
    return app.test_client()

@pytest.fixture
def test_users(db):
    admin = User(username='test_admin', role='ADMINISTRATOR', is_active=True)
    admin.set_password('admin123')

    reception = User(username='test_reception', role='RECEPTIONIST', is_active=True)
    reception.set_password('reception123')

    doc_user = User(username='test_doctor', role='DOCTOR', is_active=True)
    doc_user.set_password('doctor123')

    db.session.add_all([admin, reception, doc_user])
    db.session.flush()

    doctor = Doctor(
        user_id=doc_user.id,
        name='Dr. Test Physician',
        title='Dr.',
        specialty='Internal Medicine',
        is_active=True
    )
    db.session.add(doctor)
    db.session.commit()

    return {
        'admin': admin,
        'reception': reception,
        'doctor_user': doc_user,
        'doctor': doctor
    }

