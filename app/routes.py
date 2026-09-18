from datetime import datetime, date, time
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from app.extensions import db
from app.models import (
    User, Doctor, Patient, PatientPhone, Encounter, EncounterHistory,
    EncounterVital, EncounterDiagnosis, Prescription, PrescriptionItem,
    Investigation, Procedure, Voucher, VoucherItem, Payment, Appointment,
    InventoryItem, InventoryTransaction, InventoryCategory,
    RegistrationNumberSetting, SirNameSetting, PatientFieldSetting, SystemSetting, AuditLog
)
from app.helpers import (
    login_required, role_required, admin_required,
    AuditService, RegistrationNumberService, PatientService,
    EncounterService, BillingService, InventoryService, AppointmentService
)

# Initialize Blueprints (Preserves exact route naming conventions for templates & tests)
auth_bp = Blueprint('auth', __name__)
patients_bp = Blueprint('patients', __name__)
encounters_bp = Blueprint('encounters', __name__)
appointments_bp = Blueprint('appointments', __name__)
doctors_bp = Blueprint('doctors', __name__)
inventory_bp = Blueprint('inventory', __name__)
billing_bp = Blueprint('billing', __name__)
dashboard_bp = Blueprint('dashboard', __name__)
reports_bp = Blueprint('reports', __name__)
administration_bp = Blueprint('administration', __name__)
settings_bp = Blueprint('settings', __name__)

all_blueprints = [
    auth_bp, patients_bp, encounters_bp, appointments_bp, doctors_bp,
    inventory_bp, billing_bp, dashboard_bp, reports_bp, administration_bp, settings_bp
]


# ==========================================
# 1. AUTHENTICATION ROUTES
# ==========================================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if '_user_id' in session:
        return redirect(url_for('patients.patients_list'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact an administrator.', 'danger')
                return render_template('auth/login.html')

            session.clear()
            session['_user_id'] = user.id
            session['user_role'] = user.role
            session['username'] = user.username

            AuditService.log('LOGIN', 'User', user.id, f"User {user.username} logged in successfully.", user_id=user.id)
            flash(f'Welcome back, {user.username}!', 'success')
            next_url = request.args.get('next')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect(url_for('patients.patients_list'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    user_id = session.get('_user_id')
    if user_id:
        AuditService.log('LOGOUT', 'User', user_id, "User logged out.", user_id=user_id)
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


# ==========================================
# 2. PATIENT ROUTES
# ==========================================

@patients_bp.route('/patients')
@login_required
def patients_list():
    query_str = request.args.get('q', '').strip()
    gender = request.args.get('gender', '').strip()
    state_region = request.args.get('state_region', '').strip()
    sort_by = request.args.get('sort_by', 'created_at')
    sort_dir = request.args.get('sort_dir', 'desc')
    page = request.args.get('page', 1, type=int)

    pagination = PatientService.search_patients(
        query_str=query_str,
        gender=gender if gender else None,
        state_region=state_region if state_region else None,
        page=page,
        per_page=15,
        sort_by=sort_by,
        sort_dir=sort_dir
    )

    sir_names = SirNameSetting.query.order_by(SirNameSetting.display_order).all()
    default_state = SystemSetting.get_value('default_state_region', 'Yangon')

    return render_template(
        'patients/list.html',
        pagination=pagination,
        patients=pagination.items,
        query_str=query_str,
        gender=gender,
        state_region=state_region,
        sort_by=sort_by,
        sort_dir=sort_dir,
        sir_names=sir_names,
        default_state=default_state,
        active_tab='patients',
        sub_view='patients'
    )


@patients_bp.route('/patients/new', methods=['GET', 'POST'])
@login_required
def new_patient():
    sir_names = SirNameSetting.query.order_by(SirNameSetting.display_order).all()
    field_settings = {s.field_name: s for s in PatientFieldSetting.query.all()}
    default_state = SystemSetting.get_value('default_state_region', 'Yangon')

    if request.method == 'POST':
        errors = PatientService.validate_required_fields(request.form)
        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template(
                'patients/new.html',
                sir_names=sir_names,
                field_settings=field_settings,
                default_state=default_state,
                form_data=request.form,
                active_tab='patients',
                sub_view='patients'
            )

        try:
            patient = PatientService.create_patient(request.form)
            AuditService.log('CREATE', 'Patient', patient.id, f"Registered patient {patient.registration_number} ({patient.full_name})")
            flash(f"Patient {patient.full_name} registered successfully with Registration No: {patient.registration_number}", 'success')

            create_initial = request.form.get('create_initial_encounter') == '1'
            if create_initial:
                return redirect(url_for('encounters.new_encounter', patient_id=patient.id, is_initial='1'))

            return redirect(url_for('patients.patient_detail', patient_id=patient.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error registering patient: {str(e)}", 'danger')

    return render_template(
        'patients/new.html',
        sir_names=sir_names,
        field_settings=field_settings,
        default_state=default_state,
        form_data={},
        active_tab='patients',
        sub_view='patients'
    )


@patients_bp.route('/patients/<int:patient_id>')
@login_required
def patient_detail(patient_id):
    """
    Patient Detail: EXACTLY FOUR BIG CARDS
    1. Overview, 2. Encounters, 3. Investigations, 4. Billing
    """
    patient = Patient.query.get_or_404(patient_id)

    latest_completed_encounter = Encounter.query.filter_by(
        patient_id=patient.id,
        status='completed'
    ).order_by(Encounter.encounter_date.desc()).first()

    current_medications = ""
    if latest_completed_encounter and latest_completed_encounter.history:
        current_medications = latest_completed_encounter.history.drug_history or ""

    encounters = patient.encounters.order_by(Encounter.encounter_date.desc()).all()
    investigations = Investigation.query.filter_by(patient_id=patient.id).order_by(Investigation.ordered_date.desc()).all()
    billing_summary = BillingService.get_patient_billing_summary(patient.id)

    return render_template(
        'patients/detail.html',
        patient=patient,
        current_medications=current_medications,
        encounters=encounters,
        investigations=investigations,
        billing_summary=billing_summary,
        active_tab='patients',
        sub_view='patients'
    )


@patients_bp.route('/patients/<int:patient_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    sir_names = SirNameSetting.query.order_by(SirNameSetting.display_order).all()
    field_settings = {s.field_name: s for s in PatientFieldSetting.query.all()}
    default_state = SystemSetting.get_value('default_state_region', 'Yangon')

    if request.method == 'POST':
        errors = PatientService.validate_required_fields(request.form)
        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template(
                'patients/edit.html',
                patient=patient,
                sir_names=sir_names,
                field_settings=field_settings,
                default_state=default_state,
                active_tab='patients',
                sub_view='patients'
            )

        try:
            PatientService.update_patient(patient, request.form)
            AuditService.log('UPDATE', 'Patient', patient.id, f"Updated demographics for {patient.registration_number}")
            flash('Patient information updated successfully.', 'success')
            return redirect(url_for('patients.patient_detail', patient_id=patient.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating patient: {str(e)}", 'danger')

    return render_template(
        'patients/edit.html',
        patient=patient,
        sir_names=sir_names,
        field_settings=field_settings,
        default_state=default_state,
        active_tab='patients',
        sub_view='patients'
    )


# ==========================================
# 3. ENCOUNTER ROUTES
# ==========================================

@encounters_bp.route('/encounters')
@login_required
def encounters_list():
    query_str = request.args.get('q', '').strip()
    doctor_id = request.args.get('doctor_id', type=int)
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    page = request.args.get('page', 1, type=int)

    q = Encounter.query.join(Patient).filter(Encounter.status != 'draft')

    if query_str:
        term = f"%{query_str}%"
        q = q.filter(
            (Patient.registration_number.ilike(term)) |
            (Patient.patient_name.ilike(term))
        )
    if doctor_id:
        q = q.filter(Encounter.doctor_id == doctor_id)
    if date_from:
        try:
            df = datetime.strptime(date_from, '%Y-%m-%d')
            q = q.filter(Encounter.encounter_date >= df)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.strptime(date_to + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
            q = q.filter(Encounter.encounter_date <= dt)
        except ValueError:
            pass

    pagination = q.order_by(Encounter.encounter_date.desc()).paginate(page=page, per_page=15, error_out=False)
    doctors = Doctor.query.filter_by(is_active=True).all()

    return render_template(
        'encounters/list.html',
        pagination=pagination,
        encounters=pagination.items,
        doctors=doctors,
        query_str=query_str,
        doctor_id=doctor_id,
        date_from=date_from,
        date_to=date_to,
        active_tab='patients',
        sub_view='encounters'
    )


@encounters_bp.route('/encounters/new')
@login_required
def new_encounter():
    patient_id = request.args.get('patient_id', type=int)
    if not patient_id:
        flash('Patient ID is required to start an encounter.', 'danger')
        return redirect(url_for('patients.patients_list'))

    patient = Patient.query.get_or_404(patient_id)
    current_user = db.session.get(User, session['_user_id'])
    doc_id = EncounterService.resolve_doctor_for_user(current_user)

    encounter = Encounter(
        patient_id=patient.id,
        doctor_id=doc_id,
        status='draft',
        encounter_date=datetime.utcnow()
    )
    db.session.add(encounter)
    db.session.flush()

    hist_data = EncounterService.copy_previous_history(patient.id)
    encounter_history = EncounterHistory(
        encounter_id=encounter.id,
        pmh=hist_data['pmh'],
        psh=hist_data['psh'],
        drug_history=hist_data['drug_history'],
        allergy_history=hist_data['allergy_history'],
        family_history=hist_data['family_history'],
        social_history=hist_data['social_history']
    )
    db.session.add(encounter_history)
    db.session.commit()

    is_initial = request.args.get('is_initial', '0')
    return redirect(url_for('encounters.encounter_detail', encounter_id=encounter.id, is_initial=is_initial))


@encounters_bp.route('/encounters/<int:encounter_id>', methods=['GET', 'POST'])
@login_required
def encounter_detail(encounter_id):
    encounter = Encounter.query.get_or_404(encounter_id)
    patient = encounter.patient
    current_user = db.session.get(User, session['_user_id'])
    doctors = Doctor.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        action = request.form.get('action', 'save')

        if action == 'cancel':
            if encounter.status == 'draft':
                EncounterService.discard_encounter_if_empty(encounter.id)
                flash('Draft encounter cancelled and discarded.', 'info')
                return redirect(url_for('patients.patient_detail', patient_id=patient.id))
            return redirect(url_for('patients.patient_detail', patient_id=patient.id))

        has_meaning = EncounterService.has_meaningful_content(encounter, request.form)
        if not has_meaning and encounter.status == 'draft':
            db.session.delete(encounter)
            db.session.commit()
            flash('No clinical data entered; draft encounter was discarded.', 'info')
            return redirect(url_for('patients.patient_detail', patient_id=patient.id))

        try:
            EncounterService.save_encounter_from_form(encounter, request.form, current_user)
            AuditService.log('SAVE', 'Encounter', encounter.id, f"Saved clinical encounter for patient {patient.registration_number}")
            flash('Encounter saved successfully.', 'success')
            return redirect(url_for('patients.patient_detail', patient_id=patient.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error saving encounter: {str(e)}", 'danger')

    previous_encounters = Encounter.query.filter(
        Encounter.patient_id == patient.id,
        Encounter.id != encounter.id,
        Encounter.status == 'completed'
    ).order_by(Encounter.encounter_date.desc()).limit(5).all()

    return render_template(
        'encounters/detail.html',
        encounter=encounter,
        patient=patient,
        current_user=current_user,
        doctors=doctors,
        previous_encounters=previous_encounters,
        active_tab='patients',
        sub_view='encounters'
    )


# ==========================================
# 4. APPOINTMENT ROUTES
# ==========================================

@appointments_bp.route('/appointments')
@login_required
def appointments_list():
    date_filter = request.args.get('date', '').strip()
    doctor_id = request.args.get('doctor_id', type=int)
    status = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)

    q = Appointment.query.join(Patient)

    if date_filter:
        try:
            d = datetime.strptime(date_filter, '%Y-%m-%d').date()
            q = q.filter(Appointment.appointment_date == d)
        except ValueError:
            pass
    if doctor_id:
        q = q.filter(Appointment.doctor_id == doctor_id)
    if status:
        q = q.filter(Appointment.status == status)

    pagination = q.order_by(Appointment.appointment_date.asc(), Appointment.appointment_time.asc()).paginate(page=page, per_page=15, error_out=False)
    doctors = Doctor.query.filter_by(is_active=True).all()

    return render_template(
        'appointments/list.html',
        pagination=pagination,
        appointments=pagination.items,
        doctors=doctors,
        date_filter=date_filter,
        doctor_id=doctor_id,
        status=status,
        active_tab='patients',
        sub_view='appointments'
    )


@appointments_bp.route('/appointments/new', methods=['GET', 'POST'])
@login_required
def new_appointment():
    patient_id = request.args.get('patient_id', type=int)
    selected_patient = db.session.get(Patient, patient_id) if patient_id else None
    doctors = Doctor.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        pid = request.form.get('patient_id', type=int)
        doc_id = request.form.get('doctor_id', type=int)
        app_date = request.form.get('appointment_date')
        app_time = request.form.get('appointment_time')
        reason = request.form.get('reason')
        notes = request.form.get('notes')

        if not pid or not app_date:
            flash('Patient and appointment date are required.', 'danger')
            return redirect(url_for('appointments.new_appointment', patient_id=pid))

        try:
            app = AppointmentService.create_appointment(
                patient_id=pid,
                appointment_date=app_date,
                appointment_time=app_time,
                doctor_id=doc_id,
                reason=reason,
                notes=notes
            )
            AuditService.log('CREATE', 'Appointment', app.id, f"Created appointment for patient ID {pid}")
            flash('Appointment scheduled successfully.', 'success')
            return redirect(url_for('appointments.appointments_list'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error creating appointment: {str(e)}", 'danger')

    patients = Patient.query.filter_by(is_active=True).order_by(Patient.patient_name).all()

    return render_template(
        'appointments/form.html',
        selected_patient=selected_patient,
        patients=patients,
        doctors=doctors,
        active_tab='patients',
        sub_view='appointments'
    )


@appointments_bp.route('/appointments/<int:appointment_id>/status', methods=['POST'])
@login_required
def update_status(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    new_status = request.form.get('status')
    if new_status in ['Scheduled', 'Confirmed', 'Completed', 'Cancelled', 'No Show']:
        appointment.status = new_status
        appointment.updated_at = datetime.utcnow()
        db.session.commit()
        flash(f"Appointment status updated to {new_status}.", 'success')
    return redirect(url_for('appointments.appointments_list'))


@appointments_bp.route('/appointments/<int:appointment_id>/start-encounter')
@login_required
def start_encounter_from_appointment(appointment_id):
    current_user = db.session.get(User, session['_user_id'])
    encounter = AppointmentService.convert_to_encounter(appointment_id, current_user)
    flash('Encounter started and linked to scheduled appointment.', 'success')
    return redirect(url_for('encounters.encounter_detail', encounter_id=encounter.id))


# ==========================================
# 5. DOCTOR ROUTES
# ==========================================

@doctors_bp.route('/doctors')
@login_required
def doctors_list():
    doctors = Doctor.query.order_by(Doctor.name.asc()).all()
    return render_template(
        'doctors/list.html',
        doctors=doctors,
        active_tab='doctors'
    )


@doctors_bp.route('/doctors/new', methods=['GET', 'POST'])
@role_required(['ADMINISTRATOR'])
def new_doctor():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        title = request.form.get('title', '').strip()
        specialty = request.form.get('specialty', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        user_id = request.form.get('user_id', type=int)

        if not name:
            flash('Doctor name is required.', 'danger')
            return redirect(url_for('doctors.new_doctor'))

        try:
            doc = Doctor(
                name=name,
                title=title,
                specialty=specialty,
                phone=phone,
                email=email,
                user_id=user_id if user_id else None,
                is_active=True
            )
            db.session.add(doc)
            db.session.commit()
            AuditService.log('CREATE', 'Doctor', doc.id, f"Added doctor {doc.name}")
            flash(f"Doctor {doc.display_name} added successfully.", 'success')
            return redirect(url_for('doctors.doctors_list'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding doctor: {str(e)}", 'danger')

    unlinked_doctor_users = User.query.filter_by(role='DOCTOR').all()
    return render_template(
        'doctors/form.html',
        doctor=None,
        users=unlinked_doctor_users,
        active_tab='doctors'
    )


@doctors_bp.route('/doctors/<int:doctor_id>/edit', methods=['GET', 'POST'])
@role_required(['ADMINISTRATOR'])
def edit_doctor(doctor_id):
    doc = Doctor.query.get_or_404(doctor_id)

    if request.method == 'POST':
        doc.name = request.form.get('name', doc.name).strip()
        doc.title = request.form.get('title', doc.title).strip()
        doc.specialty = request.form.get('specialty', doc.specialty).strip()
        doc.phone = request.form.get('phone', doc.phone).strip()
        doc.email = request.form.get('email', doc.email).strip()
        doc.is_active = request.form.get('is_active') == '1'
        u_id = request.form.get('user_id', type=int)
        doc.user_id = u_id if u_id else None

        try:
            db.session.commit()
            AuditService.log('UPDATE', 'Doctor', doc.id, f"Updated doctor {doc.name}")
            flash('Doctor details updated successfully.', 'success')
            return redirect(url_for('doctors.doctors_list'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating doctor: {str(e)}", 'danger')

    unlinked_doctor_users = User.query.filter_by(role='DOCTOR').all()
    return render_template(
        'doctors/form.html',
        doctor=doc,
        users=unlinked_doctor_users,
        active_tab='doctors'
    )


# ==========================================
# 6. INVENTORY & PHARMACY ROUTES
# ==========================================

@inventory_bp.route('/inventory')
@login_required
def inventory_list():
    query_str = request.args.get('q', '').strip()
    category_id = request.args.get('category_id', type=int)
    low_stock = request.args.get('low_stock') == '1'
    page = request.args.get('page', 1, type=int)

    q = InventoryItem.query
    if query_str:
        term = f"%{query_str}%"
        q = q.filter(
            (InventoryItem.item_name.ilike(term)) |
            (InventoryItem.generic_name.ilike(term)) |
            (InventoryItem.brand.ilike(term))
        )
    if category_id:
        q = q.filter(InventoryItem.category_id == category_id)
    if low_stock:
        q = q.filter(InventoryItem.quantity <= InventoryItem.reorder_level)

    pagination = q.order_by(InventoryItem.item_name.asc()).paginate(page=page, per_page=15, error_out=False)
    categories = InventoryCategory.query.order_by(InventoryCategory.name).all()

    return render_template(
        'inventory/list.html',
        pagination=pagination,
        items=pagination.items,
        categories=categories,
        query_str=query_str,
        category_id=category_id,
        low_stock=low_stock,
        active_tab='inventory'
    )


@inventory_bp.route('/inventory/items/new', methods=['GET', 'POST'])
@login_required
def new_item():
    categories = InventoryCategory.query.order_by(InventoryCategory.name).all()

    if request.method == 'POST':
        item_name = request.form.get('item_name', '').strip()
        generic_name = request.form.get('generic_name', '').strip()
        brand = request.form.get('brand', '').strip()
        category_id = request.form.get('category_id', type=int)
        unit = request.form.get('unit', '').strip()
        batch_number = request.form.get('batch_number', '').strip()
        expiry_date = request.form.get('expiry_date')
        initial_qty = request.form.get('quantity', 0.0)
        purchase_price = request.form.get('purchase_price', 0.0)
        selling_price = request.form.get('selling_price', 0.0)
        reorder_level = request.form.get('reorder_level', 10.0)

        if not item_name:
            flash('Item name is required.', 'danger')
            return redirect(url_for('inventory.new_item'))

        exp = None
        if expiry_date:
            try:
                exp = datetime.strptime(expiry_date, '%Y-%m-%d').date()
            except ValueError:
                pass

        try:
            item = InventoryItem(
                item_name=item_name,
                generic_name=generic_name or None,
                brand=brand or None,
                category_id=category_id if category_id else None,
                unit=unit or None,
                batch_number=batch_number or None,
                expiry_date=exp,
                quantity=float(initial_qty or 0.0),
                purchase_price=float(purchase_price or 0.0),
                selling_price=float(selling_price or 0.0),
                reorder_level=float(reorder_level or 10.0),
                is_active=True
            )
            db.session.add(item)
            db.session.flush()

            if item.quantity > 0:
                txn = InventoryTransaction(
                    item_id=item.id,
                    transaction_type='IN',
                    quantity=item.quantity,
                    balance_after=item.quantity,
                    reference='Initial Stock',
                    notes='Initial inventory registration'
                )
                db.session.add(txn)

            db.session.commit()
            AuditService.log('CREATE', 'InventoryItem', item.id, f"Added inventory item {item.item_name} with stock {item.quantity}")
            flash(f"Item {item.item_name} registered successfully.", 'success')
            return redirect(url_for('inventory.inventory_list'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error registering item: {str(e)}", 'danger')

    return render_template(
        'inventory/form.html',
        item=None,
        categories=categories,
        active_tab='inventory'
    )


@inventory_bp.route('/inventory/items/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_item(item_id):
    item = InventoryItem.query.get_or_404(item_id)
    categories = InventoryCategory.query.order_by(InventoryCategory.name).all()

    if request.method == 'POST':
        item.item_name = request.form.get('item_name', item.item_name).strip()
        item.generic_name = request.form.get('generic_name', '').strip() or None
        item.brand = request.form.get('brand', '').strip() or None
        cid = request.form.get('category_id', type=int)
        item.category_id = cid if cid else None
        item.unit = request.form.get('unit', '').strip() or None
        item.batch_number = request.form.get('batch_number', '').strip() or None
        exp = request.form.get('expiry_date')
        if exp:
            try:
                item.expiry_date = datetime.strptime(exp, '%Y-%m-%d').date()
            except ValueError:
                pass
        item.purchase_price = float(request.form.get('purchase_price', item.purchase_price) or 0.0)
        item.selling_price = float(request.form.get('selling_price', item.selling_price) or 0.0)
        item.reorder_level = float(request.form.get('reorder_level', item.reorder_level) or 10.0)
        item.is_active = request.form.get('is_active') == '1'

        try:
            db.session.commit()
            AuditService.log('UPDATE', 'InventoryItem', item.id, f"Updated item {item.item_name}")
            flash('Item updated successfully.', 'success')
            return redirect(url_for('inventory.inventory_list'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating item: {str(e)}", 'danger')

    return render_template(
        'inventory/form.html',
        item=item,
        categories=categories,
        active_tab='inventory'
    )


@inventory_bp.route('/inventory/items/<int:item_id>/transactions', methods=['POST'])
@login_required
def stock_transaction(item_id):
    transaction_type = request.form.get('transaction_type')
    quantity = request.form.get('quantity')
    reference = request.form.get('reference')
    notes = request.form.get('notes')

    try:
        txn = InventoryService.record_stock_transaction(
            item_id=item_id,
            transaction_type=transaction_type,
            quantity=quantity,
            reference=reference,
            notes=notes
        )
        AuditService.log('STOCK_TXN', 'InventoryItem', item_id, f"{transaction_type} {quantity} units (Balance: {txn.balance_after})")
        flash(f"Stock movement recorded. Current balance: {txn.balance_after}", 'success')
    except Exception as e:
        flash(f"Stock transaction failed: {str(e)}", 'danger')

    return redirect(url_for('inventory.inventory_list'))


# ==========================================
# 7. BILLING & VOUCHER ROUTES
# ==========================================

@billing_bp.route('/billing/vouchers')
@login_required
def vouchers_list():
    status = request.args.get('status', '').strip()
    query_str = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)

    q = Voucher.query.join(Patient)
    if status:
        q = q.filter(Voucher.status == status)
    if query_str:
        term = f"%{query_str}%"
        q = q.filter(
            (Voucher.voucher_number.ilike(term)) |
            (Patient.patient_name.ilike(term)) |
            (Patient.registration_number.ilike(term))
        )

    pagination = q.order_by(Voucher.voucher_date.desc()).paginate(page=page, per_page=15, error_out=False)

    return render_template(
        'billing/list.html',
        pagination=pagination,
        vouchers=pagination.items,
        status=status,
        query_str=query_str,
        active_tab='patients',
        sub_view='patients'
    )


@billing_bp.route('/billing/vouchers/new', methods=['GET', 'POST'])
@login_required
def new_voucher():
    encounter_id = request.args.get('encounter_id', type=int)
    if not encounter_id and request.method == 'GET':
        flash('Encounter must be selected to create a voucher.', 'warning')
        return redirect(url_for('patients.patients_list'))

    encounter = Encounter.query.get_or_404(encounter_id)
    patient = encounter.patient

    if request.method == 'POST':
        descriptions = request.form.getlist('item_desc[]')
        quantities = request.form.getlist('item_qty[]')
        prices = request.form.getlist('item_price[]')
        discount = request.form.get('discount', 0.0)
        notes = request.form.get('notes', '')

        items_data = []
        for idx, desc in enumerate(descriptions):
            if desc and desc.strip():
                try:
                    qty = float(quantities[idx]) if idx < len(quantities) else 1.0
                    price = float(prices[idx]) if idx < len(prices) else 0.0
                    items_data.append({
                        'description': desc.strip(),
                        'quantity': qty,
                        'unit_price': price
                    })
                except ValueError:
                    continue

        if not items_data:
            flash('At least one item or service is required on the voucher.', 'danger')
            return render_template(
                'billing/form.html',
                encounter=encounter,
                patient=patient,
                active_tab='patients',
                sub_view='patients'
            )

        try:
            voucher = BillingService.create_voucher(
                encounter_id=encounter.id,
                items_data=items_data,
                discount=discount,
                notes=notes
            )
            AuditService.log('CREATE', 'Voucher', voucher.id, f"Generated voucher {voucher.voucher_number} for total {voucher.total}")
            flash(f"Voucher {voucher.voucher_number} created successfully.", 'success')
            return redirect(url_for('billing.voucher_detail', voucher_id=voucher.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error generating voucher: {str(e)}", 'danger')

    return render_template(
        'billing/form.html',
        encounter=encounter,
        patient=patient,
        active_tab='patients',
        sub_view='patients'
    )


@billing_bp.route('/billing/vouchers/<int:voucher_id>', methods=['GET', 'POST'])
@login_required
def voucher_detail(voucher_id):
    voucher = Voucher.query.get_or_404(voucher_id)

    if request.method == 'POST':
        amount = request.form.get('amount')
        payment_method = request.form.get('payment_method', 'Cash')
        reference = request.form.get('reference')
        notes = request.form.get('notes')

        try:
            payment = BillingService.record_payment(
                voucher_id=voucher.id,
                amount=amount,
                payment_method=payment_method,
                reference=reference,
                notes=notes
            )
            AuditService.log('PAYMENT', 'Voucher', voucher.id, f"Recorded payment {payment.amount} via {payment.payment_method}")
            flash('Payment recorded successfully.', 'success')
            return redirect(url_for('billing.voucher_detail', voucher_id=voucher.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error recording payment: {str(e)}", 'danger')

    return render_template(
        'billing/detail.html',
        voucher=voucher,
        patient=voucher.patient,
        encounter=voucher.encounter,
        active_tab='patients',
        sub_view='patients'
    )


# ==========================================
# 8. DASHBOARD ROUTES
# ==========================================

@dashboard_bp.route('/dashboard')
@login_required
def index():
    today = date.today()
    start_of_today = datetime.combine(today, time.min)
    end_of_today = datetime.combine(today, time.max)

    current_user = db.session.get(User, session['_user_id'])

    today_registrations = Patient.query.filter(Patient.created_at >= start_of_today, Patient.created_at <= end_of_today).count()
    today_encounters = Encounter.query.filter(Encounter.encounter_date >= start_of_today, Encounter.encounter_date <= end_of_today, Encounter.status != 'draft').count()
    today_appointments = Appointment.query.filter(Appointment.appointment_date == today).count()
    pending_investigations = Investigation.query.filter(Investigation.status.in_(['Ordered', 'Pending'])).count()

    today_vouchers = Voucher.query.filter(Voucher.voucher_date >= start_of_today, Voucher.voucher_date <= end_of_today).all()
    today_billed = sum(v.total for v in today_vouchers)

    today_payments = Payment.query.filter(Payment.payment_date >= start_of_today, Payment.payment_date <= end_of_today).all()
    today_collected = sum(p.amount for p in today_payments)

    low_stock_items = InventoryItem.query.filter(
        InventoryItem.is_active == True,
        InventoryItem.quantity <= InventoryItem.reorder_level
    ).limit(8).all()

    doctor_today_appointments = []
    doctor_recent_encounters = []
    if current_user.is_doctor() and current_user.doctor_profile:
        doc_id = current_user.doctor_profile.id
        doctor_today_appointments = Appointment.query.filter_by(
            doctor_id=doc_id,
            appointment_date=today
        ).order_by(Appointment.appointment_time.asc()).all()

        doctor_recent_encounters = Encounter.query.filter_by(
            doctor_id=doc_id
        ).order_by(Encounter.encounter_date.desc()).limit(8).all()

    recent_encounters = Encounter.query.filter(Encounter.status != 'draft').order_by(Encounter.encounter_date.desc()).limit(6).all()

    return render_template(
        'dashboard/index.html',
        current_user=current_user,
        today=today,
        today_registrations=today_registrations,
        today_encounters=today_encounters,
        today_appointments=today_appointments,
        pending_investigations=pending_investigations,
        today_billed=today_billed,
        today_collected=today_collected,
        low_stock_items=low_stock_items,
        doctor_today_appointments=doctor_today_appointments,
        doctor_recent_encounters=doctor_recent_encounters,
        recent_encounters=recent_encounters,
        active_tab='dashboard'
    )


# ==========================================
# 9. REPORTS ROUTES
# ==========================================

@reports_bp.route('/reports')
@login_required
def index():
    report_type = request.args.get('type', 'registrations')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    doctor_id = request.args.get('doctor_id', type=int)

    df = None
    dt = None
    if date_from:
        try:
            df = datetime.strptime(date_from, '%Y-%m-%d')
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.strptime(date_to + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass

    results = []
    doctors = Doctor.query.filter_by(is_active=True).all()

    if report_type == 'registrations':
        q = Patient.query
        if df:
            q = q.filter(Patient.created_at >= df)
        if dt:
            q = q.filter(Patient.created_at <= dt)
        results = q.order_by(Patient.created_at.desc()).limit(100).all()

    elif report_type == 'encounters':
        q = Encounter.query.filter(Encounter.status != 'draft')
        if df:
            q = q.filter(Encounter.encounter_date >= df)
        if dt:
            q = q.filter(Encounter.encounter_date <= dt)
        if doctor_id:
            q = q.filter(Encounter.doctor_id == doctor_id)
        results = q.order_by(Encounter.encounter_date.desc()).limit(100).all()

    elif report_type == 'appointments':
        q = Appointment.query
        if df:
            q = q.filter(Appointment.appointment_date >= df.date())
        if dt:
            q = q.filter(Appointment.appointment_date <= dt.date())
        if doctor_id:
            q = q.filter(Appointment.doctor_id == doctor_id)
        results = q.order_by(Appointment.appointment_date.desc()).limit(100).all()

    elif report_type == 'investigations':
        q = Investigation.query
        if df:
            q = q.filter(Investigation.ordered_date >= df)
        if dt:
            q = q.filter(Investigation.ordered_date <= dt)
        results = q.order_by(Investigation.ordered_date.desc()).limit(100).all()

    elif report_type == 'prescriptions':
        q = PrescriptionItem.query.join(Prescription)
        if df:
            q = q.filter(Prescription.created_at >= df)
        if dt:
            q = q.filter(Prescription.created_at <= dt)
        results = q.order_by(Prescription.created_at.desc()).limit(100).all()

    elif report_type == 'billing':
        q = Voucher.query
        if df:
            q = q.filter(Voucher.voucher_date >= df)
        if dt:
            q = q.filter(Voucher.voucher_date <= dt)
        results = q.order_by(Voucher.voucher_date.desc()).limit(100).all()

    elif report_type == 'collections':
        q = Payment.query
        if df:
            q = q.filter(Payment.payment_date >= df)
        if dt:
            q = q.filter(Payment.payment_date <= dt)
        results = q.order_by(Payment.payment_date.desc()).limit(100).all()

    elif report_type == 'inventory':
        results = InventoryItem.query.order_by(InventoryItem.quantity.asc()).limit(100).all()

    return render_template(
        'reports/index.html',
        report_type=report_type,
        date_from=date_from,
        date_to=date_to,
        doctor_id=doctor_id,
        doctors=doctors,
        results=results,
        active_tab='reports'
    )


# ==========================================
# 10. ADMINISTRATION & AUDIT ROUTES
# ==========================================

@administration_bp.route('/administration')
@administration_bp.route('/administration/users')
@admin_required
def users_list():
    users = User.query.order_by(User.id.asc()).all()
    return render_template(
        'administration/users.html',
        users=users,
        active_tab='administration',
        admin_sub='users'
    )


@administration_bp.route('/administration/users/new', methods=['GET', 'POST'])
@admin_required
def new_user():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'RECEPTIONIST')

        if not username or not password:
            flash('Username and password are required.', 'danger')
            return redirect(url_for('administration.new_user'))

        existing = User.query.filter_by(username=username).first()
        if existing:
            flash('Username already exists.', 'danger')
            return redirect(url_for('administration.new_user'))

        try:
            user = User(
                username=username,
                role=role,
                is_active=True
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            AuditService.log('CREATE', 'User', user.id, f"Admin created user {user.username} with role {user.role}")
            flash(f"User {user.username} created successfully.", 'success')
            return redirect(url_for('administration.users_list'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error creating user: {str(e)}", 'danger')

    return render_template(
        'administration/user_form.html',
        user=None,
        active_tab='administration',
        admin_sub='users'
    )


@administration_bp.route('/administration/users/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        user.role = request.form.get('role', user.role)
        user.is_active = request.form.get('is_active') == '1'

        new_pass = request.form.get('new_password', '').strip()
        if new_pass:
            user.set_password(new_pass)

        try:
            db.session.commit()
            AuditService.log('UPDATE', 'User', user.id, f"Admin updated user {user.username}")
            flash('User updated successfully.', 'success')
            return redirect(url_for('administration.users_list'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating user: {str(e)}", 'danger')

    return render_template(
        'administration/user_form.html',
        user=user,
        active_tab='administration',
        admin_sub='users'
    )


@administration_bp.route('/administration/audit')
@admin_required
def audit_logs():
    page = request.args.get('page', 1, type=int)
    action_filter = request.args.get('action', '')
    entity_filter = request.args.get('entity', '')

    q = AuditLog.query
    if action_filter:
        q = q.filter(AuditLog.action == action_filter)
    if entity_filter:
        q = q.filter(AuditLog.entity_type == entity_filter)

    pagination = q.order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=20, error_out=False)

    return render_template(
        'administration/audit.html',
        pagination=pagination,
        logs=pagination.items,
        action_filter=action_filter,
        entity_filter=entity_filter,
        active_tab='administration',
        admin_sub='audit'
    )


# ==========================================
# 11. GLOBAL SETTINGS ROUTES
# ==========================================

@settings_bp.route('/settings', methods=['GET', 'POST'])
@admin_required
def index():
    reg_setting = RegistrationNumberSetting.query.first()
    if not reg_setting:
        reg_setting = RegistrationNumberSetting(
            format_pattern='REG-{YYYY}-{NUMBER}',
            increment_amount=1,
            next_number=1,
            padding=6
        )
        db.session.add(reg_setting)
        db.session.commit()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'save_reg_settings':
            reg_setting.format_pattern = request.form.get('format_pattern', 'REG-{YYYY}-{NUMBER}').strip()
            reg_setting.increment_amount = int(request.form.get('increment_amount', 1))
            reg_setting.next_number = int(request.form.get('next_number', 1))
            reg_setting.padding = int(request.form.get('padding', 6))
            reg_setting.updated_at = datetime.utcnow()
            db.session.commit()
            AuditService.log('UPDATE', 'Settings', reg_setting.id, "Updated registration number configuration")
            flash('Registration number settings saved.', 'success')

        elif action == 'save_field_settings':
            fields = PatientFieldSetting.query.all()
            for f in fields:
                req_val = request.form.get(f'req_{f.field_name}') == '1'
                f.is_required = req_val
            db.session.commit()
            AuditService.log('UPDATE', 'Settings', None, "Updated patient required fields settings")
            flash('Field requirement settings saved.', 'success')

        elif action == 'save_system_settings':
            default_state = request.form.get('default_state_region', 'Yangon').strip()
            SystemSetting.set_value('default_state_region', default_state)
            AuditService.log('UPDATE', 'Settings', None, f"Updated default state/region to {default_state}")
            flash('System settings saved.', 'success')

        elif action == 'add_sir_name':
            title = request.form.get('sir_name_title', '').strip()
            gender = request.form.get('sir_name_gender', 'Male')
            if title:
                existing = SirNameSetting.query.filter_by(title=title).first()
                if not existing:
                    sn = SirNameSetting(title=title, default_gender=gender, is_default=True, display_order=50)
                    db.session.add(sn)
                    db.session.commit()
                    flash(f"Sir Name '{title}' added with default gender {gender}.", 'success')
                else:
                    flash(f"Sir Name '{title}' already exists.", 'warning')

        return redirect(url_for('settings.index'))

    sir_names = SirNameSetting.query.order_by(SirNameSetting.display_order.asc()).all()
    field_settings = PatientFieldSetting.query.all()
    default_state = SystemSetting.get_value('default_state_region', 'Yangon')
    preview_no = RegistrationNumberService.preview_number()

    return render_template(
        'settings/index.html',
        reg_setting=reg_setting,
        preview_no=preview_no,
        sir_names=sir_names,
        field_settings=field_settings,
        default_state=default_state,
        active_tab='settings'
    )


@settings_bp.route('/settings/sir-names/<int:sn_id>/delete', methods=['POST'])
@admin_required
def delete_sir_name(sn_id):
    sn = SirNameSetting.query.get_or_404(sn_id)
    db.session.delete(sn)
    db.session.commit()
    flash(f"Sir Name '{sn.title}' removed.", 'info')
    return redirect(url_for('settings.index'))
