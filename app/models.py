import calendar
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db

# ==========================================
# 1. USER & AUTHENTICATION
# ==========================================

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(32), nullable=False, default='RECEPTIONIST')  # ADMINISTRATOR, DOCTOR, RECEPTIONIST
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 1-to-1 optional relationship to Doctor profile
    doctor_profile = db.relationship('Doctor', backref='user', uselist=False, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_administrator(self):
        return self.role == 'ADMINISTRATOR'

    def is_doctor(self):
        return self.role == 'DOCTOR'

    def is_receptionist(self):
        return self.role == 'RECEPTIONIST'

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


# ==========================================
# 2. DOCTOR DIRECTORY
# ==========================================

class Doctor(db.Model):
    __tablename__ = 'doctors'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, unique=True)
    name = db.Column(db.String(128), nullable=False, index=True)
    title = db.Column(db.String(64), nullable=True)  # e.g., Dr., Consultant Physician
    specialty = db.Column(db.String(128), nullable=True)
    phone = db.Column(db.String(64), nullable=True)
    email = db.Column(db.String(128), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    encounters = db.relationship('Encounter', backref='doctor', lazy='dynamic')
    appointments = db.relationship('Appointment', backref='doctor', lazy='dynamic')

    @property
    def display_name(self):
        if self.title:
            return f"{self.title} {self.name}"
        return self.name

    def __repr__(self):
        return f"<Doctor {self.name}>"


# ==========================================
# 3. PATIENTS & PHONES
# ==========================================

class Patient(db.Model):
    __tablename__ = 'patients'

    id = db.Column(db.Integer, primary_key=True)
    registration_number = db.Column(db.String(64), unique=True, nullable=False, index=True)

    # Myanmar Naming
    sir_name = db.Column(db.String(32), nullable=False)
    patient_name = db.Column(db.String(128), nullable=False, index=True)

    # Demographics
    gender = db.Column(db.String(16), nullable=False)  # 'Male', 'Female'
    date_of_birth = db.Column(db.Date, nullable=True, index=True)
    marital_status = db.Column(db.String(32), nullable=True)
    occupation = db.Column(db.String(128), nullable=True)
    blood_group = db.Column(db.String(16), nullable=True)

    # Guardian Info
    guardian_name = db.Column(db.String(128), nullable=True)
    guardian_relationship = db.Column(db.String(64), nullable=True)
    guardian_phone = db.Column(db.String(64), nullable=True)

    # Identification
    nrc_number = db.Column(db.String(64), nullable=True, index=True)

    # Contact Info
    email = db.Column(db.String(128), nullable=True)
    address = db.Column(db.Text, nullable=True)
    city_township = db.Column(db.String(128), nullable=True)
    state_region = db.Column(db.String(128), nullable=True)

    # Patient Summary & Notes
    patient_summary = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Normalized phone numbers
    phones = db.relationship(
        'PatientPhone',
        backref='patient',
        cascade='all, delete-orphan',
        lazy='selectin',
        order_by='desc(PatientPhone.is_primary), PatientPhone.id'
    )

    encounters = db.relationship(
        'Encounter',
        backref='patient',
        lazy='dynamic',
        order_by='desc(Encounter.encounter_date)'
    )

    appointments = db.relationship(
        'Appointment',
        backref='patient',
        lazy='dynamic',
        order_by='desc(Appointment.appointment_date)'
    )

    investigations = db.relationship(
        'Investigation',
        backref='patient',
        lazy='dynamic',
        order_by='desc(Investigation.ordered_date)'
    )

    vouchers = db.relationship(
        'Voucher',
        backref='patient',
        lazy='dynamic',
        order_by='desc(Voucher.voucher_date)'
    )

    @property
    def full_name(self):
        return f"{self.sir_name} {self.patient_name}".strip()

    @property
    def primary_phone(self):
        if self.phones:
            for p in self.phones:
                if p.is_primary:
                    return p.phone_number
            return self.phones[0].phone_number
        return ""

    @property
    def phone_numbers_list(self):
        return [p.phone_number for p in self.phones]

    def get_dynamic_age(self, ref_date=None):
        """Calendar-aware dynamic age calculation. Returns dict and formatted string."""
        if not self.date_of_birth:
            return None
        if ref_date is None:
            ref_date = date.today()

        dob = self.date_of_birth
        if dob > ref_date:
            return {'years': 0, 'months': 0, 'days': 0, 'formatted': '0 Days'}

        years = ref_date.year - dob.year
        months = ref_date.month - dob.month
        days = ref_date.day - dob.day

        if days < 0:
            prev_month = ref_date.month - 1 if ref_date.month > 1 else 12
            prev_year = ref_date.year if ref_date.month > 1 else ref_date.year - 1
            days_in_prev_month = calendar.monthrange(prev_year, prev_month)[1]
            days += days_in_prev_month
            months -= 1

        if months < 0:
            years -= 1
            months += 12

        parts = []
        if years > 0:
            parts.append(f"{years} {'Year' if years == 1 else 'Years'}")
        if months > 0:
            parts.append(f"{months} {'Month' if months == 1 else 'Months'}")
        if days > 0 or not parts:
            parts.append(f"{days} {'Day' if days == 1 else 'Days'}")

        formatted = " ".join(parts)
        return {
            'years': years,
            'months': months,
            'days': days,
            'formatted': formatted
        }

    @property
    def age_formatted(self):
        res = self.get_dynamic_age()
        return res['formatted'] if res else "Unknown"

    def __repr__(self):
        return f"<Patient {self.registration_number}: {self.full_name}>"


class PatientPhone(db.Model):
    __tablename__ = 'patient_phones'

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False, index=True)
    phone_number = db.Column(db.String(64), nullable=False, index=True)
    is_primary = db.Column(db.Boolean, default=False, nullable=False)
    label = db.Column(db.String(32), nullable=True)  # Primary, Alternative, etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<PatientPhone {self.phone_number} (patient_id={self.patient_id})>"


# ==========================================
# 4. ENCOUNTERS & CLINICAL CONSULTATION
# ==========================================

class Encounter(db.Model):
    __tablename__ = 'encounters'

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='RESTRICT'), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id', ondelete='SET NULL'), nullable=True, index=True)
    encounter_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    status = db.Column(db.String(32), default='completed', nullable=False)  # 'draft', 'completed', 'cancelled'

    # Clinical workspace core
    hopi = db.Column(db.Text, nullable=True)
    examination = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Encounter-specific independent history snapshot
    history = db.relationship(
        'EncounterHistory',
        backref='encounter',
        uselist=False,
        cascade='all, delete-orphan'
    )

    # Structured components
    vitals = db.relationship(
        'EncounterVital',
        backref='encounter',
        cascade='all, delete-orphan',
        lazy='selectin',
        order_by='desc(EncounterVital.recorded_at)'
    )

    diagnoses = db.relationship(
        'EncounterDiagnosis',
        backref='encounter',
        cascade='all, delete-orphan',
        lazy='selectin',
        order_by='EncounterDiagnosis.order_index'
    )

    prescriptions = db.relationship(
        'Prescription',
        backref='encounter',
        cascade='all, delete-orphan',
        lazy='selectin'
    )

    investigations_rel = db.relationship(
        'Investigation',
        backref='encounter',
        cascade='all, delete-orphan',
        lazy='selectin'
    )

    procedures = db.relationship(
        'Procedure',
        backref='encounter',
        cascade='all, delete-orphan',
        lazy='selectin'
    )

    vouchers = db.relationship(
        'Voucher',
        backref='encounter',
        lazy='dynamic',
        order_by='desc(Voucher.voucher_date)'
    )

    appointment = db.relationship(
        'Appointment',
        backref=db.backref('linked_encounter', uselist=False),
        uselist=False
    )

    @property
    def latest_vitals(self):
        return self.vitals[0] if self.vitals else None

    @property
    def diagnoses_summary(self):
        if not self.diagnoses:
            return "No diagnosis recorded"
        return ", ".join([d.diagnosis_text for d in self.diagnoses])

    def __repr__(self):
        return f"<Encounter #{self.id} (Patient {self.patient_id})>"


class EncounterHistory(db.Model):
    __tablename__ = 'encounter_histories'

    id = db.Column(db.Integer, primary_key=True)
    encounter_id = db.Column(db.Integer, db.ForeignKey('encounters.id', ondelete='CASCADE'), unique=True, nullable=False)
    pmh = db.Column(db.Text, nullable=True)             # Past Medical History
    psh = db.Column(db.Text, nullable=True)             # Past Surgical History
    drug_history = db.Column(db.Text, nullable=True)    # Drug History
    allergy_history = db.Column(db.Text, nullable=True) # Allergy History
    family_history = db.Column(db.Text, nullable=True)  # Family History
    social_history = db.Column(db.Text, nullable=True)  # Social History
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def is_empty(self):
        fields = [self.pmh, self.psh, self.drug_history, self.allergy_history, self.family_history, self.social_history]
        return not any(f and f.strip() for f in fields)


class EncounterVital(db.Model):
    __tablename__ = 'encounter_vitals'

    id = db.Column(db.Integer, primary_key=True)
    encounter_id = db.Column(db.Integer, db.ForeignKey('encounters.id', ondelete='CASCADE'), nullable=False, index=True)
    bp_systolic = db.Column(db.Integer, nullable=True)
    bp_diastolic = db.Column(db.Integer, nullable=True)
    pulse = db.Column(db.Integer, nullable=True)
    temperature = db.Column(db.Float, nullable=True)
    spo2 = db.Column(db.Integer, nullable=True)
    respiratory_rate = db.Column(db.Integer, nullable=True)
    weight = db.Column(db.Float, nullable=True)
    notes = db.Column(db.String(255), nullable=True)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @property
    def bp_display(self):
        if self.bp_systolic and self.bp_diastolic:
            return f"{self.bp_systolic}/{self.bp_diastolic} mmHg"
        return "N/A"

    def is_empty(self):
        return not any([
            self.bp_systolic, self.bp_diastolic, self.pulse,
            self.temperature, self.spo2, self.respiratory_rate,
            self.weight, self.notes
        ])


class EncounterDiagnosis(db.Model):
    __tablename__ = 'encounter_diagnoses'

    id = db.Column(db.Integer, primary_key=True)
    encounter_id = db.Column(db.Integer, db.ForeignKey('encounters.id', ondelete='CASCADE'), nullable=False, index=True)
    diagnosis_text = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(64), nullable=True)  # Primary, Secondary, Provisional, Confirmed
    notes = db.Column(db.Text, nullable=True)
    order_index = db.Column(db.Integer, default=0, nullable=False)


# ==========================================
# 5. PRESCRIPTIONS & MEDICATIONS
# ==========================================

class Prescription(db.Model):
    __tablename__ = 'prescriptions'

    id = db.Column(db.Integer, primary_key=True)
    encounter_id = db.Column(db.Integer, db.ForeignKey('encounters.id', ondelete='CASCADE'), nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False, index=True)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(32), default='Prescribed', nullable=False)  # Prescribed, Dispensed, Cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    items = db.relationship('PrescriptionItem', backref='prescription', cascade='all, delete-orphan', lazy='selectin')

    def __repr__(self):
        return f"<Prescription #{self.id} for Encounter #{self.encounter_id}>"


class PrescriptionItem(db.Model):
    __tablename__ = 'prescription_items'

    id = db.Column(db.Integer, primary_key=True)
    prescription_id = db.Column(db.Integer, db.ForeignKey('prescriptions.id', ondelete='CASCADE'), nullable=False, index=True)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_items.id', ondelete='SET NULL'), nullable=True)

    medicine_name = db.Column(db.String(255), nullable=False)
    dose = db.Column(db.String(64), nullable=True)          # e.g., 500 mg
    route = db.Column(db.String(64), nullable=True)        # Oral, IV, IM, etc.
    frequency = db.Column(db.String(64), nullable=True)    # BD, TDS, QDS, PRN
    duration = db.Column(db.String(64), nullable=True)      # 5 days
    quantity = db.Column(db.Float, nullable=True)          # 10
    instructions = db.Column(db.Text, nullable=True)       # After food

    inventory_item = db.relationship('InventoryItem', backref='prescription_items')


# ==========================================
# 6. INVESTIGATIONS & PROCEDURES
# ==========================================

class Investigation(db.Model):
    __tablename__ = 'investigations'

    id = db.Column(db.Integer, primary_key=True)
    encounter_id = db.Column(db.Integer, db.ForeignKey('encounters.id', ondelete='CASCADE'), nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False, index=True)

    investigation_name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(32), default='Ordered', nullable=False)  # Ordered, Pending, Completed, Cancelled
    ordered_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    result = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Investigation {self.investigation_name} ({self.status})>"


class Procedure(db.Model):
    __tablename__ = 'procedures'

    id = db.Column(db.Integer, primary_key=True)
    encounter_id = db.Column(db.Integer, db.ForeignKey('encounters.id', ondelete='CASCADE'), nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id', ondelete='SET NULL'), nullable=True)

    procedure_name = db.Column(db.String(255), nullable=False)
    procedure_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status = db.Column(db.String(32), default='Completed', nullable=False)  # Scheduled, In Progress, Completed, Cancelled
    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    doctor = db.relationship('Doctor', backref='performed_procedures')

    def __repr__(self):
        return f"<Procedure {self.procedure_name}>"


# ==========================================
# 7. BILLING & PAYMENTS
# ==========================================

class Voucher(db.Model):
    __tablename__ = 'vouchers'

    id = db.Column(db.Integer, primary_key=True)
    voucher_number = db.Column(db.String(64), unique=True, nullable=False, index=True)
    encounter_id = db.Column(db.Integer, db.ForeignKey('encounters.id', ondelete='RESTRICT'), nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='RESTRICT'), nullable=False, index=True)
    voucher_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    status = db.Column(db.String(32), default='unpaid', nullable=False)  # unpaid, partially_paid, fully_paid, cancelled
    subtotal = db.Column(db.Float, default=0.0, nullable=False)
    discount = db.Column(db.Float, default=0.0, nullable=False)
    total = db.Column(db.Float, default=0.0, nullable=False)
    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    items = db.relationship('VoucherItem', backref='voucher', cascade='all, delete-orphan', lazy='selectin')
    payments = db.relationship('Payment', backref='voucher', cascade='all, delete-orphan', lazy='selectin')

    @property
    def total_paid(self):
        return sum(p.amount for p in self.payments)

    @property
    def balance_due(self):
        return max(0.0, self.total - self.total_paid)

    def update_status_and_totals(self):
        self.subtotal = sum(item.amount for item in self.items)
        self.total = max(0.0, self.subtotal - (self.discount or 0.0))
        paid = self.total_paid
        if paid >= self.total and self.total > 0:
            self.status = 'fully_paid'
        elif paid > 0:
            self.status = 'partially_paid'
        else:
            self.status = 'unpaid'

    def __repr__(self):
        return f"<Voucher {self.voucher_number} Total={self.total}>"


class VoucherItem(db.Model):
    __tablename__ = 'voucher_items'

    id = db.Column(db.Integer, primary_key=True)
    voucher_id = db.Column(db.Integer, db.ForeignKey('vouchers.id', ondelete='CASCADE'), nullable=False, index=True)
    description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Float, default=1.0, nullable=False)
    unit_price = db.Column(db.Float, default=0.0, nullable=False)
    amount = db.Column(db.Float, default=0.0, nullable=False)

    def calculate_amount(self):
        self.amount = (self.quantity or 0.0) * (self.unit_price or 0.0)
        return self.amount


class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    voucher_id = db.Column(db.Integer, db.ForeignKey('vouchers.id', ondelete='CASCADE'), nullable=False, index=True)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    amount = db.Column(db.Float, default=0.0, nullable=False)
    payment_method = db.Column(db.String(64), default='Cash', nullable=False)  # Cash, Bank, Mobile Payment, Other
    reference = db.Column(db.String(128), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Payment #{self.id} Amount={self.amount} ({self.payment_method})>"


# ==========================================
# 8. APPOINTMENTS
# ==========================================

class Appointment(db.Model):
    __tablename__ = 'appointments'

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id', ondelete='SET NULL'), nullable=True, index=True)
    encounter_id = db.Column(db.Integer, db.ForeignKey('encounters.id', ondelete='SET NULL'), nullable=True)

    appointment_date = db.Column(db.Date, nullable=False, index=True)
    appointment_time = db.Column(db.Time, nullable=True)
    status = db.Column(db.String(32), default='Scheduled', nullable=False)  # Scheduled, Confirmed, Completed, Cancelled, No Show
    reason = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    @property
    def formatted_time(self):
        if self.appointment_time:
            return self.appointment_time.strftime('%I:%M %p')
        return "Unspecified"

    def __repr__(self):
        return f"<Appointment #{self.id} on {self.appointment_date} ({self.status})>"


# ==========================================
# 9. PHARMACY & INVENTORY
# ==========================================

class InventoryCategory(db.Model):
    __tablename__ = 'inventory_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=True)

    items = db.relationship('InventoryItem', backref='category', lazy='dynamic')

    def __repr__(self):
        return f"<InventoryCategory {self.name}>"


class InventoryItem(db.Model):
    __tablename__ = 'inventory_items'

    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(255), nullable=False, index=True)
    generic_name = db.Column(db.String(255), nullable=True)
    brand = db.Column(db.String(128), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('inventory_categories.id', ondelete='SET NULL'), nullable=True)
    unit = db.Column(db.String(64), nullable=True)  # Tab, Cap, Bottle, Vial, etc.
    batch_number = db.Column(db.String(64), nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)

    quantity = db.Column(db.Float, default=0.0, nullable=False)
    purchase_price = db.Column(db.Float, default=0.0, nullable=False)
    selling_price = db.Column(db.Float, default=0.0, nullable=False)
    reorder_level = db.Column(db.Float, default=10.0, nullable=False)

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    transactions = db.relationship('InventoryTransaction', backref='item', cascade='all, delete-orphan', lazy='dynamic')

    @property
    def is_low_stock(self):
        return self.quantity <= self.reorder_level

    def __repr__(self):
        return f"<InventoryItem {self.item_name} (Qty={self.quantity})>"


class InventoryTransaction(db.Model):
    __tablename__ = 'inventory_transactions'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('inventory_items.id', ondelete='CASCADE'), nullable=False, index=True)
    transaction_type = db.Column(db.String(32), nullable=False)  # 'IN', 'OUT', 'ADJUSTMENT'
    quantity = db.Column(db.Float, nullable=False)
    balance_after = db.Column(db.Float, nullable=False)
    reference = db.Column(db.String(128), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<InventoryTransaction #{self.id} Item={self.item_id} Type={self.transaction_type} Qty={self.quantity}>"


# ==========================================
# 10. CONFIGURATION & SETTINGS
# ==========================================

class RegistrationNumberSetting(db.Model):
    __tablename__ = 'registration_number_settings'

    id = db.Column(db.Integer, primary_key=True)
    format_pattern = db.Column(db.String(64), default='REG-{YYYY}-{NUMBER}', nullable=False)
    increment_amount = db.Column(db.Integer, default=1, nullable=False)
    next_number = db.Column(db.Integer, default=1, nullable=False)
    padding = db.Column(db.Integer, default=6, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<RegistrationNumberSetting pattern={self.format_pattern} next={self.next_number}>"


class SirNameSetting(db.Model):
    __tablename__ = 'sir_names'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(32), unique=True, nullable=False)
    default_gender = db.Column(db.String(16), nullable=False)  # 'Male' or 'Female'
    is_default = db.Column(db.Boolean, default=True, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)

    def __repr__(self):
        return f"<SirName {self.title} -> {self.default_gender}>"


class PatientFieldSetting(db.Model):
    __tablename__ = 'patient_field_settings'

    id = db.Column(db.Integer, primary_key=True)
    field_name = db.Column(db.String(64), unique=True, nullable=False)
    label = db.Column(db.String(128), nullable=False)
    is_required = db.Column(db.Boolean, default=False, nullable=False)
    is_visible = db.Column(db.Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<PatientFieldSetting {self.field_name} required={self.is_required}>"


class SystemSetting(db.Model):
    __tablename__ = 'system_settings'

    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(64), unique=True, nullable=False)
    setting_value = db.Column(db.Text, nullable=True)

    @classmethod
    def get_value(cls, key, default=None):
        item = cls.query.filter_by(setting_key=key).first()
        return item.setting_value if item and item.setting_value is not None else default

    @classmethod
    def set_value(cls, key, value):
        item = cls.query.filter_by(setting_key=key).first()
        if not item:
            item = cls(setting_key=key)
            db.session.add(item)
        item.setting_value = str(value)
        db.session.commit()


# ==========================================
# 11. AUDIT TRAIL LOG
# ==========================================

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    user_username = db.Column(db.String(64), nullable=True)
    action = db.Column(db.String(64), nullable=False)        # CREATE, UPDATE, DELETE, LOGIN, LOGOUT, SAVE
    entity_type = db.Column(db.String(64), nullable=False)   # Patient, Encounter, Voucher, User, Setting, Doctor, Appointment
    entity_id = db.Column(db.String(64), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    summary = db.Column(db.Text, nullable=True)

    user = db.relationship('User', backref='audit_logs')

    def __repr__(self):
        return f"<AuditLog #{self.id} {self.action} on {self.entity_type} {self.entity_id}>"
