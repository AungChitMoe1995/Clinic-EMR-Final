import re
import calendar
import math
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlsplit
from sqlalchemy import update
from datetime import datetime, date, timedelta
from functools import wraps
from flask import session, redirect, url_for, flash, request, abort, current_app
from sqlalchemy import or_, desc, asc
from app.extensions import db
from app.models import (
    User, Doctor, Patient, PatientPhone, Encounter, EncounterHistory,
    EncounterVital, EncounterDiagnosis, Prescription, PrescriptionItem,
    Investigation, Procedure, Voucher, VoucherItem, Payment, Appointment,
    InventoryItem, InventoryTransaction, InventoryCategory,
    RegistrationNumberSetting, SirNameSetting, PatientFieldSetting, SystemSetting, AuditLog,
    utcnow
)

# ==========================================
# 1. AUTHENTICATION DECORATORS
# ==========================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if user is None or not user.is_active:
            session.clear()
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.full_path))
        return f(*args, **kwargs)
    return decorated_function


def role_required(allowed_roles=None):
    # This deployment intentionally shares clinic access across authenticated staff.
    # Role labels describe staff profiles; they do not enforce segregation of duties.
    return login_required


def admin_required(f):
    return login_required(f)


def safe_next_url(value):
    if not value or not value.startswith('/') or value.startswith('//') or '\\' in value:
        return None
    parsed = urlsplit(value)
    return value if not parsed.scheme and not parsed.netloc else None


def finite_number(value, label, minimum=0, maximum=None, integer=False, optional=False):
    if value is None or str(value).strip() == '':
        if optional:
            return None
        raise ValueError(f'{label} is required.')
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError(f'{label} must be a number.') from None
    if not math.isfinite(result) or result < minimum or (maximum is not None and result > maximum):
        raise ValueError(f'{label} is outside the allowed range.')
    if integer and not result.is_integer():
        raise ValueError(f'{label} must be a whole number.')
    return int(result) if integer else result


def money(value, label):
    number = finite_number(value, label, maximum=1_000_000_000_000)
    return Decimal(str(number)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def get_current_user():
    """Returns the authenticated Account or User instance, caching on flask.g for matching session."""
    from flask import g, session
    sess_key = (session.get('_account_id'), session.get('_user_id'))
    if not any(sess_key):
        return None
    if getattr(g, '_current_user_sess_key', None) == sess_key and getattr(g, 'current_user', None) is not None:
        return g.current_user

    user = None
    if '_account_id' in session:
        from app.models import Account
        user = db.session.get(Account, session['_account_id'])
    elif '_user_id' in session:
        from app.models import User
        user = db.session.get(User, session['_user_id'])

    g._current_user_sess_key = sess_key
    g.current_user = user
    return user


# ==========================================
# 1.1 REQUEST-LOCAL QUERY CACHING
# ==========================================


def get_cached(key, getter, ttl=60):
    from flask import g
    cache = g.setdefault('_query_cache', {})
    if key not in cache:
        cache[key] = getter()
    return cache[key]


def invalidate_cache(key=None):
    from flask import g
    cache = g.setdefault('_query_cache', {})
    if key:
        cache.pop(key, None)
    else:
        cache.clear()


def get_active_doctors():
    return get_cached('active_doctors', lambda: Doctor.query.filter_by(is_active=True).all(), ttl=120)

def get_active_inventory():
    return get_cached('active_inventory', lambda: InventoryItem.query.filter_by(is_active=True).order_by(InventoryItem.item_name.asc()).all(), ttl=60)



# ==========================================
# 2. AUDIT LOGGING HELPER
# ==========================================

class AuditService:
    @staticmethod
    def log(action, entity_type, entity_id=None, summary=None, user_id=None):
        """Creates a lightweight clinical audit trail record."""
        try:
            username = session.get('username')
            if user_id is None:
                # user_id foreign key references users.id (None for account sessions)
                user_id = session.get('_user_id')

            log_entry = AuditLog(
                user_id=user_id if isinstance(user_id, int) else None,
                user_username=username or 'Clinic Account',
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
                summary=summary,
                timestamp=utcnow()
            )
            db.session.add(log_entry)
            db.session.commit()
        except Exception:
            db.session.rollback()
            pass


# ==========================================
# 3. REGISTRATION NUMBER GENERATOR
# ==========================================

class RegistrationNumberService:
    @staticmethod
    def preview_number(format_pattern=None, next_number=None, padding=None, ref_date=None):
        """Generates a sample preview of the registration number without committing or incrementing."""
        if ref_date is None:
            ref_date = date.today()

        setting = None
        if format_pattern is None or next_number is None or padding is None:
            setting = RegistrationNumberSetting.query.first()

        pattern = format_pattern if format_pattern is not None else (setting.format_pattern if setting else 'REG-{YYYY}-{NUMBER}')
        num = next_number if next_number is not None else (setting.next_number if setting else 1)
        pad = padding if padding is not None else (setting.padding if setting else 6)

        num_str = str(num).zfill(int(pad))
        yyyy_str = ref_date.strftime('%Y')
        yy_str = ref_date.strftime('%y')
        mm_str = ref_date.strftime('%m')
        dd_str = ref_date.strftime('%d')

        preview = (
            pattern.replace('{NUMBER}', num_str)
                   .replace('{YYYY}', yyyy_str)
                   .replace('{YY}', yy_str)
                   .replace('{MM}', mm_str)
                   .replace('{DD}', dd_str)
        )
        return preview

    @classmethod
    def allocate_next_number(cls, max_retries=5):
        """
        Safely generates the next human-facing patient registration number.
        Advances counter by configured increment amount.
        """
        now = date.today()
        yyyy_str = now.strftime('%Y')
        yy_str = now.strftime('%y')
        mm_str = now.strftime('%m')
        dd_str = now.strftime('%d')

        for attempt in range(max_retries):
            try:
                setting = db.session.query(RegistrationNumberSetting).with_for_update().first()
                if not setting:
                    setting = RegistrationNumberSetting(
                        format_pattern='REG-{YYYY}-{NUMBER}',
                        increment_amount=1,
                        next_number=1,
                        padding=6
                    )
                    db.session.add(setting)
                    db.session.flush()

                current_val = setting.next_number
                pad = setting.padding or 6
                increment = setting.increment_amount or 1
                pattern = setting.format_pattern or 'REG-{YYYY}-{NUMBER}'

                num_str = str(current_val).zfill(pad)
                reg_no = (
                    pattern.replace('{NUMBER}', num_str)
                           .replace('{YYYY}', yyyy_str)
                           .replace('{YY}', yy_str)
                           .replace('{MM}', mm_str)
                           .replace('{DD}', dd_str)
                )

                if increment < 1 or current_val < 1 or not 1 <= pad <= 12 or '{NUMBER}' not in pattern:
                    raise ValueError('Registration format requires {NUMBER}, positive counters, and padding 1-12.')
                changed = db.session.execute(update(RegistrationNumberSetting).where(
                    RegistrationNumberSetting.id == setting.id, RegistrationNumberSetting.next_number == current_val
                ).values(next_number=current_val + increment, updated_at=utcnow()).execution_options(synchronize_session=False))
                if changed.rowcount != 1:
                    db.session.rollback()
                    continue
                db.session.commit()
                return reg_no
            except Exception as e:
                db.session.rollback()
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Failed to allocate registration number after {max_retries} attempts: {str(e)}")

        raise RuntimeError("Failed to allocate registration number.")


# ==========================================
# 4. PATIENT BUSINESS LOGIC
# ==========================================

class PatientService:
    @staticmethod
    def calculate_dob_from_age(years=0, months=0, days=0, ref_date=None):
        """Calculates approximate Date of Birth from age (years, months, days)."""
        if ref_date is None:
            ref_date = date.today()

        try:
            years = int(years or 0)
            months = int(months or 0)
            days = int(days or 0)
        except (ValueError, TypeError):
            return None

        if min(years, months, days) < 0 or years > 150 or months > 11 or days > 31:
            raise ValueError('Enter a nonnegative age with months 0-11 and days 0-31.')
        total_months = ref_date.month - months
        year_offset = 0
        while total_months <= 0:
            total_months += 12
            year_offset += 1

        target_year = ref_date.year - years - year_offset
        target_month = total_months
        max_days = calendar.monthrange(target_year, target_month)[1]
        target_day = min(ref_date.day, max_days)

        approx_date = date(target_year, target_month, target_day) - timedelta(days=days)
        return approx_date

    @classmethod
    def normalize_and_set_phones(cls, patient, phone_input):
        """
        Parses multi-phone input (comma, semicolon, newline or slash separated)
        into normalized PatientPhone records.
        """
        if not phone_input:
            patient.phones = []
            return

        raw_tokens = re.split(r'[,;\n/]+', str(phone_input))
        cleaned_numbers = [t.strip() for t in raw_tokens if t.strip()]

        new_phones = []
        for idx, num in enumerate(cleaned_numbers):
            phone_record = PatientPhone(
                patient_id=patient.id,
                phone_number=num,
                is_primary=(idx == 0),
                label='Primary' if idx == 0 else f'Alternative {idx}'
            )
            new_phones.append(phone_record)

        patient.phones = new_phones

    @classmethod
    def validate_required_fields(cls, form_data):
        """Validates configurable required fields against PatientFieldSetting."""
        field_settings = PatientFieldSetting.query.filter_by(is_required=True).all()
        errors = []
        for setting in field_settings:
            val = form_data.get(setting.field_name)
            if not val or not str(val).strip():
                errors.append(f"{setting.label} is required.")
        return errors

    @classmethod
    def create_patient(cls, data, commit=True):
        """
        Creates a new Patient record with safely allocated registration number
        and normalized phone records.
        """
        reg_number = RegistrationNumberService.allocate_next_number()

        dob = None
        if data.get('date_of_birth'):
            try:
                dob = datetime.strptime(data['date_of_birth'], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                raise ValueError('Date of birth must be a valid YYYY-MM-DD date.') from None
        elif data.get('age_years') or data.get('age_months') or data.get('age_days'):
            dob = cls.calculate_dob_from_age(
                data.get('age_years', 0),
                data.get('age_months', 0),
                data.get('age_days', 0)
            )

        if dob and dob > date.today():
            raise ValueError('Date of birth cannot be in the future.')
        if not (data.get('patient_name') or '').strip():
            raise ValueError('Patient name is required.')
        patient = Patient(
            registration_number=reg_number,
            sir_name=data.get('sir_name', '').strip(),
            patient_name=data.get('patient_name', '').strip(),
            gender=data.get('gender', 'Male').strip(),
            date_of_birth=dob,
            marital_status=data.get('marital_status', '').strip() or None,
            occupation=data.get('occupation', '').strip() or None,
            blood_group=data.get('blood_group', '').strip() or None,
            guardian_name=data.get('guardian_name', '').strip() or None,
            guardian_relationship=data.get('guardian_relationship', '').strip() or None,
            guardian_phone=data.get('guardian_phone', '').strip() or None,
            nrc_number=data.get('nrc_number', '').strip() or None,
            email=data.get('email', '').strip() or None,
            address=data.get('address', '').strip() or None,
            city_township=data.get('city_township', '').strip() or None,
            state_region=data.get('state_region', '').strip() or None,
            patient_summary=data.get('patient_summary', '').strip() or None,
            notes=data.get('notes', '').strip() or None,
            is_active=True
        )

        db.session.add(patient)
        db.session.flush()

        cls.normalize_and_set_phones(patient, data.get('phone_number', ''))
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return patient

    @classmethod
    def update_patient(cls, patient, data):
        """Updates an existing patient's details and normalized phone records."""
        patient.sir_name = data.get('sir_name', patient.sir_name).strip()
        patient.patient_name = data.get('patient_name', patient.patient_name).strip()
        patient.gender = data.get('gender', patient.gender).strip()

        if data.get('date_of_birth'):
            try:
                patient.date_of_birth = datetime.strptime(data['date_of_birth'], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                raise ValueError('Date of birth must be valid.') from None
        elif data.get('age_years') is not None and (data.get('age_years') or data.get('age_months') or data.get('age_days')):
            patient.date_of_birth = cls.calculate_dob_from_age(
                data.get('age_years', 0),
                data.get('age_months', 0),
                data.get('age_days', 0)
            )

        if patient.date_of_birth and patient.date_of_birth > date.today():
            raise ValueError('Date of birth cannot be in the future.')
        if not patient.patient_name:
            raise ValueError('Patient name is required.')
        patient.marital_status = data.get('marital_status', patient.marital_status)
        patient.occupation = data.get('occupation', patient.occupation)
        patient.blood_group = data.get('blood_group', patient.blood_group)
        patient.guardian_name = data.get('guardian_name', patient.guardian_name)
        patient.guardian_relationship = data.get('guardian_relationship', patient.guardian_relationship)
        patient.guardian_phone = data.get('guardian_phone', patient.guardian_phone)
        patient.nrc_number = data.get('nrc_number', patient.nrc_number)
        patient.email = data.get('email', patient.email)
        patient.address = data.get('address', patient.address)
        patient.city_township = data.get('city_township', patient.city_township)
        patient.state_region = data.get('state_region', patient.state_region)
        patient.patient_summary = data.get('patient_summary', patient.patient_summary)
        patient.notes = data.get('notes', patient.notes)

        if 'phone_number' in data:
            cls.normalize_and_set_phones(patient, data.get('phone_number', ''))

        patient.updated_at = utcnow()
        db.session.commit()
        return patient

    @classmethod
    def search_patients(cls, query_str=None, gender=None, state_region=None, page=1, per_page=15, sort_by='created_at', sort_dir='desc'):
        """Server-side indexed search and pagination."""
        q = Patient.query.filter_by(is_active=True)

        if query_str and query_str.strip():
            term = f"%{query_str.strip()}%"
            phone_patient_ids = db.select(PatientPhone.patient_id).filter(
                PatientPhone.phone_number.ilike(term)
            )

            q = q.filter(
                or_(
                    Patient.registration_number.ilike(term),
                    Patient.patient_name.ilike(term),
                    Patient.nrc_number.ilike(term),
                    Patient.id.in_(phone_patient_ids)
                )
            )

        if gender:
            q = q.filter(Patient.gender == gender)
        if state_region:
            q = q.filter(Patient.state_region == state_region)

        sort_col = getattr(Patient, sort_by, Patient.created_at)
        if sort_dir == 'asc':
            q = q.order_by(asc(sort_col))
        else:
            q = q.order_by(desc(sort_col))

        return q.paginate(page=page, per_page=per_page, error_out=False)


# ==========================================
# 5. ENCOUNTER BUSINESS LOGIC
# ==========================================

class EncounterService:
    @staticmethod
    def snapshot(encounter):
        def row(obj):
            return {c.name: (getattr(obj, c.name).isoformat() if isinstance(getattr(obj,c.name), (date, datetime)) else getattr(obj,c.name)) for c in obj.__table__.columns}
        return dict(record=row(encounter), history=row(encounter.history) if encounter.history else None,
            vitals=[row(v) for v in encounter.vitals], diagnoses=[row(v) for v in encounter.diagnoses],
            prescriptions=[dict(record=row(rx), items=[row(v) for v in rx.items]) for rx in encounter.prescriptions],
            investigations=[row(v) for v in encounter.investigations_rel], procedures=[row(v) for v in encounter.procedures])

    @classmethod
    def create_draft(cls, patient, user, selected_doctor_id=None):
        if not patient.is_active:
            raise ValueError('This patient is inactive.')
        encounter = Encounter(patient_id=patient.id, doctor_id=cls.resolve_doctor_for_user(user, selected_doctor_id), status='draft')
        encounter.history = EncounterHistory(**cls.copy_previous_history(patient.id))
        db.session.add(encounter)
        db.session.flush()
        return encounter

    @classmethod
    def resolve_doctor_for_user(cls, user, selected_doctor_id=None):
        """
        Enforces doctor auto-assignment rule:
        If current logged-in user is a Doctor, encounter is automatically assigned to that doctor.
        """
        if selected_doctor_id:
            doc = db.session.get(Doctor, int(selected_doctor_id))
            if not doc or not doc.is_active:
                raise ValueError('Select an active doctor.')
            return doc.id
        if user and user.doctor_profile and user.doctor_profile.is_active:
            return user.doctor_profile.id

        return None

    @classmethod
    def copy_previous_history(cls, patient_id):
        """
        Copies past medical history from the most recent completed encounter.
        DOES NOT copy HOPI.
        """
        prev_encounter = Encounter.query.filter_by(
            patient_id=patient_id,
            status='completed'
        ).order_by(Encounter.encounter_date.desc(), Encounter.id.desc()).first()

        if prev_encounter and prev_encounter.history:
            h = prev_encounter.history
            return {
                'pmh': h.pmh or '',
                'psh': h.psh or '',
                'drug_history': h.drug_history or '',
                'allergy_history': h.allergy_history or '',
                'family_history': h.family_history or '',
                'social_history': h.social_history or ''
            }
        return {
            'pmh': '',
            'psh': '',
            'drug_history': '',
            'allergy_history': '',
            'family_history': '',
            'social_history': ''
        }

    @classmethod
    def has_meaningful_content(cls, encounter, data=None):
        """
        Determines whether the encounter contains genuine clinical content.
        Automatically copied history does NOT count as meaningful content.
        """
        if data:
            hopi = (data.get('hopi') or '').strip()
            exam = (data.get('examination') or '').strip()
            if hopi or exam:
                return True

            diagnoses = data.getlist('diagnosis_text[]') if hasattr(data, 'getlist') else data.get('diagnosis_text', [])
            if any(d.strip() for d in diagnoses if isinstance(d, str)):
                return True

            vital_fields = ['bp_systolic', 'bp_diastolic', 'pulse', 'temperature', 'spo2', 'respiratory_rate', 'weight', 'height', 'rbs']
            if any(data.get(k) and str(data.get(k)).strip() for k in vital_fields):
                return True

            medicines = data.getlist('medicine_name[]') if hasattr(data, 'getlist') else data.get('medicine_name', [])
            if any(m.strip() for m in medicines if isinstance(m, str)):
                return True

            investigations = data.getlist('investigation_name[]') if hasattr(data, 'getlist') else data.get('investigation_name', [])
            if any(inv.strip() for inv in investigations if isinstance(inv, str)):
                return True

            procedures = data.getlist('procedure_name[]') if hasattr(data, 'getlist') else data.get('procedure_name', [])
            if any(p.strip() for p in procedures if isinstance(p, str)):
                return True

            prev_hist = cls.copy_previous_history(encounter.patient_id)
            for k in ['pmh', 'psh', 'drug_history', 'allergy_history', 'family_history', 'social_history']:
                val = (data.get(k) or '').strip()
                if val and val != (prev_hist.get(k) or '').strip():
                    return True

            return False

        if (encounter.hopi and encounter.hopi.strip()) or (encounter.examination and encounter.examination.strip()):
            return True
        if encounter.diagnoses and len(encounter.diagnoses) > 0:
            return True
        if encounter.vitals and any(not v.is_empty() for v in encounter.vitals):
            return True
        if encounter.prescriptions and any(len(p.items) > 0 for p in encounter.prescriptions):
            return True
        if encounter.investigations_rel and len(encounter.investigations_rel) > 0:
            return True
        if encounter.procedures and len(encounter.procedures) > 0:
            return True

        if encounter.history and encounter.status == 'completed':
            return any(getattr(encounter.history, k) for k in ['pmh','psh','drug_history','allergy_history','family_history','social_history'])
        return False

    @classmethod
    def discard_encounter_if_empty(cls, encounter_id):
        """Discards encounter if it has no meaningful content."""
        encounter = db.session.get(Encounter, encounter_id)
        if not encounter:
            return True

        if encounter.status != 'draft' or encounter.vouchers.count():
            return False
        if not cls.has_meaningful_content(encounter):
            if encounter.appointment:
                appointment = encounter.appointment
                appointment.linked_encounter = None
                appointment.status = 'Scheduled'
            db.session.delete(encounter)
            db.session.commit()
            return True
        return False

    @classmethod
    def save_encounter_from_form(cls, encounter, form_data, current_user):
        """Saves full clinical encounter details from the unified Encounter workspace."""
        if form_data.get('record_version') and str(encounter.version) != form_data['record_version']:
            raise ValueError('Another user saved this encounter. Reload it before applying your changes.')
        before = cls.snapshot(encounter)
        if form_data.get('doctor_id'):
            encounter.doctor_id = cls.resolve_doctor_for_user(None, form_data['doctor_id'])
        elif encounter.doctor_id is None:
            encounter.doctor_id = cls.resolve_doctor_for_user(current_user)
        vital_fields = ['bp_systolic', 'bp_diastolic', 'pulse', 'temperature', 'spo2', 'respiratory_rate', 'weight', 'height', 'rbs']
        values = {k: finite_number(form_data.get(k), k.replace('_', ' ').title(),
                    maximum=100 if k == 'spo2' else None,
                    integer=k in ['bp_systolic','bp_diastolic','pulse','spo2','respiratory_rate'], optional=True)
                  for k in vital_fields}
        if values['height'] == 0:
            raise ValueError('Height must be greater than zero when recorded.')

        encounter.hopi = form_data.get('hopi', '').strip() or None
        encounter.examination = form_data.get('examination', '').strip() or None
        encounter.status = 'completed'

        if not encounter.history:
            encounter.history = EncounterHistory(encounter_id=encounter.id)

        encounter.history.pmh = form_data.get('pmh', '').strip() or None
        encounter.history.psh = form_data.get('psh', '').strip() or None
        encounter.history.drug_history = form_data.get('drug_history', '').strip() or None
        encounter.history.allergy_history = form_data.get('allergy_history', '').strip() or None
        encounter.history.family_history = form_data.get('family_history', '').strip() or None
        encounter.history.social_history = form_data.get('social_history', '').strip() or None

        # Clearing all vital inputs clears the stored values too.
        vital = encounter.latest_vitals
        if any(v is not None for v in values.values()) or vital is not None:
            vital = vital or EncounterVital(encounter_id=encounter.id)
            for key, value in values.items():
                setattr(vital, key, value)
            if vital not in encounter.vitals:
                encounter.vitals.append(vital)

        diag_texts = form_data.getlist('diagnosis_text[]') if hasattr(form_data, 'getlist') else []
        diag_cats = form_data.getlist('diagnosis_category[]') if hasattr(form_data, 'getlist') else []
        diag_notes = form_data.getlist('diagnosis_notes[]') if hasattr(form_data, 'getlist') else []

        encounter.diagnoses = []
        for idx, text in enumerate(diag_texts):
            if text and text.strip():
                cat = diag_cats[idx] if idx < len(diag_cats) else 'Primary'
                nt = diag_notes[idx] if idx < len(diag_notes) else None
                diag = EncounterDiagnosis(
                    encounter_id=encounter.id,
                    diagnosis_text=text.strip(),
                    category=cat.strip() if cat else None,
                    notes=nt.strip() if nt else None,
                    order_index=idx
                )
                encounter.diagnoses.append(diag)

        med_names = form_data.getlist('medicine_name[]') if hasattr(form_data, 'getlist') else []
        doses = form_data.getlist('dose[]') if hasattr(form_data, 'getlist') else []
        routes = form_data.getlist('route[]') if hasattr(form_data, 'getlist') else []
        freqs = form_data.getlist('frequency[]') if hasattr(form_data, 'getlist') else []
        durations = form_data.getlist('duration[]') if hasattr(form_data, 'getlist') else []
        quantities = form_data.getlist('quantity[]') if hasattr(form_data, 'getlist') else []
        instructions = form_data.getlist('instructions[]') if hasattr(form_data, 'getlist') else []

        encounter.prescriptions = []
        rx_items = []
        for idx, med in enumerate(med_names):
            if med and med.strip():
                qty = None
                if idx < len(quantities) and quantities[idx]:
                    try:
                        qty = finite_number(quantities[idx], 'Prescription quantity', minimum=0.000001)
                    except ValueError:
                        raise

                item = PrescriptionItem(
                    medicine_name=med.strip(),
                    dose=doses[idx].strip() if idx < len(doses) and doses[idx] else None,
                    route=routes[idx].strip() if idx < len(routes) and routes[idx] else None,
                    frequency=freqs[idx].strip() if idx < len(freqs) and freqs[idx] else None,
                    duration=durations[idx].strip() if idx < len(durations) and durations[idx] else None,
                    quantity=qty,
                    instructions=instructions[idx].strip() if idx < len(instructions) and instructions[idx] else None,
                )
                rx_items.append(item)

        if rx_items:
            rx = Prescription(
                encounter_id=encounter.id,
                patient_id=encounter.patient_id,
                status='Prescribed'
            )
            rx.items = rx_items
            encounter.prescriptions.append(rx)

        inv_names = form_data.getlist('investigation_name[]') if hasattr(form_data, 'getlist') else []
        inv_statuses = form_data.getlist('investigation_status[]') if hasattr(form_data, 'getlist') else []
        inv_results = form_data.getlist('investigation_result[]') if hasattr(form_data, 'getlist') else []

        encounter.investigations_rel = []
        for idx, iname in enumerate(inv_names):
            if iname and iname.strip():
                status_val = inv_statuses[idx].strip() if idx < len(inv_statuses) and inv_statuses[idx] else 'Ordered'
                if status_val not in ['Ordered', 'Pending', 'Completed', 'Cancelled']:
                    raise ValueError('Select a valid investigation status.')
                res_val = inv_results[idx].strip() if idx < len(inv_results) and inv_results[idx] else None
                inv = Investigation(
                    encounter_id=encounter.id,
                    patient_id=encounter.patient_id,
                    investigation_name=iname.strip(),
                    status=status_val,
                    result=res_val
                )
                encounter.investigations_rel.append(inv)

        proc_names = form_data.getlist('procedure_name[]') if hasattr(form_data, 'getlist') else []
        proc_statuses = form_data.getlist('procedure_status[]') if hasattr(form_data, 'getlist') else []
        proc_notes = form_data.getlist('procedure_notes[]') if hasattr(form_data, 'getlist') else []

        encounter.procedures = []
        for idx, pname in enumerate(proc_names):
            if pname and pname.strip():
                pstat = proc_statuses[idx].strip() if idx < len(proc_statuses) and proc_statuses[idx] else 'Completed'
                if pstat not in ['Scheduled', 'In Progress', 'Completed', 'Cancelled']:
                    raise ValueError('Select a valid procedure status.')
                pnote = proc_notes[idx].strip() if idx < len(proc_notes) and proc_notes[idx] else None
                proc = Procedure(
                    encounter_id=encounter.id,
                    patient_id=encounter.patient_id,
                    procedure_name=pname.strip(),
                    status=pstat,
                    notes=pnote,
                    doctor_id=encounter.doctor_id
                )
                encounter.procedures.append(proc)

        if encounter.appointment:
            encounter.appointment.status = 'Completed'
        encounter.updated_at = utcnow()
        db.session.flush()
        actor = current_user
        db.session.add(AuditLog(
            user_id=actor.id if isinstance(actor, User) else None,
            user_username=getattr(actor, 'username', None) or 'Clinic staff',
            action='REVISION', entity_type='Encounter', entity_id=str(encounter.id),
            summary=json.dumps({'before': before, 'after': cls.snapshot(encounter)}, ensure_ascii=False),
        ))
        db.session.commit()
        return encounter


# ==========================================
# 6. BILLING BUSINESS LOGIC
# ==========================================

class BillingService:
    @classmethod
    def generate_voucher_number(cls):
        """Generates an independent, unique voucher number."""
        today = date.today()
        prefix = f"VCH-{today.strftime('%Y%m%d')}-"

        latest = Voucher.query.filter(Voucher.voucher_number.like(f"{prefix}%")).order_by(Voucher.id.desc()).first()
        if latest:
            try:
                suffix = int(latest.voucher_number.replace(prefix, ''))
                next_num = suffix + 1
            except ValueError:
                next_num = 1
        else:
            next_num = 1

        return f"{prefix}{str(next_num).zfill(4)}"

    @classmethod
    def create_voucher(cls, encounter_id, items_data, discount=0.0, notes=None):
        """Creates a voucher linked to an encounter. Patient is inferred from encounter."""
        encounter = Encounter.query.get_or_404(encounter_id)
        if encounter.status != 'completed':
            raise ValueError('Complete the clinical encounter before creating a voucher.')
        parsed = []
        for item in items_data:
            description = (item.get('description') or '').strip()
            if not description:
                raise ValueError('Each billing line needs a description.')
            quantity = Decimal(str(finite_number(item.get('quantity', 1), 'Quantity', minimum=0.000001, maximum=1_000_000)))
            price = money(item.get('unit_price', 0), 'Unit price')
            amount = (quantity * price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            parsed.append((description, quantity, price, amount))
        if not parsed:
            raise ValueError('At least one billing item is required.')
        discount = money(discount or 0, 'Discount')
        subtotal = sum((i[3] for i in parsed), Decimal('0'))
        if discount > subtotal:
            raise ValueError('Discount cannot exceed the subtotal.')
        voucher = Voucher(voucher_number=cls.generate_voucher_number(), encounter_id=encounter.id,
            patient_id=encounter.patient_id, discount=float(discount), notes=notes)
        voucher.items = [VoucherItem(description=desc, quantity=float(qty), unit_price=float(price), amount=float(amount)) for desc,qty,price,amount in parsed]
        db.session.add(voucher)
        voucher.update_status_and_totals()
        db.session.commit()
        return voucher

    @classmethod
    def record_payment(cls, voucher_id, amount, payment_method='Cash', reference=None, notes=None):
        voucher = db.session.execute(db.select(Voucher).where(Voucher.id == voucher_id).with_for_update()).scalar_one_or_none()
        if not voucher:
            raise ValueError('Voucher not found.')
        if voucher.status == 'cancelled':
            raise ValueError('Payments cannot be added to a cancelled voucher.')
        amount = money(amount, 'Payment')
        if amount <= 0:
            raise ValueError('Payment amount must be greater than zero.')
        if amount > money(voucher.balance_due, 'Balance due'):
            raise ValueError('Payment exceeds the outstanding balance.')
        if payment_method not in ['Cash', 'Bank', 'Mobile Payment', 'Other']:
            raise ValueError('Select a valid payment method.')
        payment = Payment(voucher=voucher, amount=float(amount), payment_method=payment_method, reference=reference, notes=notes)
        # Append explicitly so calculations include the new payment before flushing.
        if payment not in voucher.payments:
            voucher.payments.append(payment)
        db.session.add(payment)
        voucher.update_status_and_totals()
        voucher.updated_at = utcnow()  # Version check serializes concurrent balance updates.
        db.session.commit()
        return payment

    @classmethod
    def get_patient_billing_summary(cls, patient_id):
        """Consolidated financial summary for Patient Detail card."""
        vouchers = Voucher.query.filter_by(patient_id=patient_id).order_by(Voucher.voucher_date.desc()).all()
        total_billed = sum(v.total for v in vouchers)
        total_paid = sum(v.total_paid for v in vouchers)
        total_outstanding = max(0.0, total_billed - total_paid)

        return {
            'vouchers': vouchers,
            'total_billed': total_billed,
            'total_paid': total_paid,
            'total_outstanding': total_outstanding
        }


# ==========================================
# 7. INVENTORY BUSINESS LOGIC
# ==========================================

class InventoryService:
    @classmethod
    def record_stock_transaction(cls, item_id, transaction_type, quantity, reference=None, notes=None):
        """
        Safely records an inventory stock movement and updates the current stock balance.
        transaction_type: 'IN', 'OUT', 'ADJUSTMENT'
        """
        item = InventoryItem.query.get_or_404(item_id)
        qty = finite_number(quantity, 'Stock quantity')
        if not item.is_active:
            raise ValueError('Cannot move stock for an inactive item.')
        if transaction_type in ['IN', 'OUT'] and qty <= 0:
            raise ValueError('Stock movement quantity must be positive.')
        if transaction_type == 'OUT' and item.expiry_date and item.expiry_date < date.today():
            raise ValueError('Cannot issue expired stock.')
        if transaction_type == 'IN':
            statement = update(InventoryItem).where(InventoryItem.id == item_id).values(quantity=InventoryItem.quantity + qty, updated_at=utcnow())
        elif transaction_type == 'OUT':
            statement = update(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.quantity >= qty).values(quantity=InventoryItem.quantity - qty, updated_at=utcnow())
        elif transaction_type == 'ADJUSTMENT':
            old = item.quantity
            statement = update(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.quantity == old).values(quantity=qty, updated_at=utcnow())
            qty -= old
        else:
            raise ValueError('Invalid stock transaction type.')
        changed = db.session.execute(statement.execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            db.session.rollback()
            raise ValueError('Insufficient stock or stock changed concurrently. Refresh and try again.')
        db.session.refresh(item)

        txn = InventoryTransaction(
            item_id=item.id,
            transaction_type=transaction_type,
            quantity=qty,
            balance_after=item.quantity,
            reference=reference,
            notes=notes
        )
        db.session.add(txn)
        db.session.commit()
        return txn

    @classmethod
    def get_low_stock_items(cls):
        """Returns items where current quantity <= reorder_level."""
        return InventoryItem.query.filter(
            InventoryItem.is_active == True,
            InventoryItem.quantity <= InventoryItem.reorder_level
        ).order_by(InventoryItem.quantity.asc()).all()


# ==========================================
# 8. APPOINTMENT BUSINESS LOGIC
# ==========================================

class AppointmentService:
    @classmethod
    def create_appointment(cls, patient_id, appointment_date, appointment_time=None, doctor_id=None, reason=None, notes=None):
        """Creates a scheduled appointment."""
        if isinstance(appointment_date, str):
            appointment_date = datetime.strptime(appointment_date, '%Y-%m-%d').date()

        if not db.session.get(Patient, patient_id):
            raise ValueError('Patient not found.')
        if doctor_id and not db.session.get(Doctor, int(doctor_id)):
            raise ValueError('Doctor not found.')
        t = None
        if appointment_time and isinstance(appointment_time, str):
            try:
                t = datetime.strptime(appointment_time, '%H:%M').time()
            except ValueError:
                raise ValueError('Appointment time must use HH:MM.') from None

        appointment = Appointment(
            patient_id=patient_id,
            doctor_id=doctor_id if doctor_id else None,
            appointment_date=appointment_date,
            appointment_time=t,
            reason=reason,
            notes=notes,
            status='Scheduled'
        )
        db.session.add(appointment)
        db.session.commit()
        return appointment

    @classmethod
    def convert_to_encounter(cls, appointment_id, user):
        """
        When a scheduled appointment becomes an actual clinical visit:
        creates an encounter linked to the appointment and updates appointment status to 'Completed'.
        """
        appointment = db.session.execute(db.select(Appointment).where(Appointment.id == appointment_id).with_for_update()).scalar_one_or_none()
        if not appointment:
            abort(404)
        if appointment.encounter_id:
            return db.session.get(Encounter, appointment.encounter_id)
        if appointment.status in ['Cancelled', 'No Show', 'Completed']:
            raise ValueError('Only an active scheduled appointment can start a visit.')
        patient = db.session.get(Patient, appointment.patient_id)
        encounter = EncounterService.create_draft(patient, user, appointment.doctor_id)

        appointment.encounter_id = encounter.id
        appointment.status = 'Confirmed'
        appointment.updated_at = utcnow()

        db.session.commit()
        return encounter
