from app.models import Patient, Encounter, Voucher, Appointment, AuditLog

def test_full_clinic_clinical_workflow(client, test_users):
    # 1. Login as Receptionist
    res_login = client.post('/login', data={
        'username': 'test_reception',
        'password': 'reception123'
    }, follow_redirects=True)
    assert res_login.status_code == 200
    assert b'Patients' in res_login.data

    # 2. Register a new patient with multiple phone numbers and Myanmar naming
    res_reg = client.post('/patients/new', data={
        'sir_name': 'U',
        'patient_name': 'Hlaing Bwar',
        'gender': 'Male',
        'date_of_birth': '1985-04-12',
        'phone_number': '09123456789, 09987654321',
        'city_township': 'Sanchaung',
        'state_region': 'Yangon',
        'patient_summary': 'Hypertension patient under regular monitoring'
    }, follow_redirects=True)
    assert res_reg.status_code == 200

    patient = Patient.query.filter_by(patient_name='Hlaing Bwar').first()
    assert patient is not None
    assert patient.sir_name == 'U'
    assert len(patient.phones) == 2
    assert patient.phones[0].phone_number == '09123456789'
    assert patient.phones[1].phone_number == '09987654321'

    # 3. View Patient Detail: Verify exactly 4 Big Cards
    res_detail = client.get(f'/patients/{patient.id}')
    assert res_detail.status_code == 200
    assert b'1. Overview &amp; Demographics' in res_detail.data or b'1. Overview' in res_detail.data
    assert b'2. Encounters' in res_detail.data
    assert b'3. Consolidated Investigations' in res_detail.data or b'3. Investigations' in res_detail.data
    assert b'4. Billing / Collections' in res_detail.data
    # Verify NO Documents card exists (Requirement 27 & 84)
    assert b'Documents' not in res_detail.data

    # 4. Doctor logs in and opens Encounter Workspace
    client.get('/logout', follow_redirects=True)
    client.post('/login', data={
        'username': 'test_doctor',
        'password': 'doctor123'
    }, follow_redirects=True)

    res_new_enc = client.get(f'/encounters/new?patient_id={patient.id}', follow_redirects=True)
    assert res_new_enc.status_code == 200
    # Verify desktop 2-column clinical hierarchy
    assert b'1. History of Present Illness (HOPI)' in res_new_enc.data
    assert b'2. Clinical Examination' in res_new_enc.data
    assert b'3. Diagnoses' in res_new_enc.data
    assert b'4. Past History' in res_new_enc.data
    assert b'Vitals' in res_new_enc.data
    assert b'Prescription' in res_new_enc.data

    # Fetch draft encounter
    draft_enc = Encounter.query.filter_by(patient_id=patient.id, status='draft').first()
    assert draft_enc is not None
    # Verify Doctor Auto-Assignment (Requirement 75)
    assert draft_enc.doctor_id == test_users['doctor'].id

    # 5. Doctor saves meaningful clinical encounter
    res_save_enc = client.post(f'/encounters/{draft_enc.id}', data={
        'action': 'save',
        'hopi': 'Severe intermittent headache for 4 days',
        'examination': 'BP 150/95 mmHg, pupil equal and reactive',
        'diagnosis_text[]': ['Essential Hypertension'],
        'diagnosis_category[]': ['Primary'],
        'bp_systolic': '150',
        'bp_diastolic': '95',
        'pulse': '78',
        'temperature': '98.4',
        'medicine_name[]': ['Amlodipine 5mg'],
        'dose[]': ['5mg'],
        'frequency[]': ['OD'],
        'duration[]': ['30 days'],
        'quantity[]': ['30'],
        'instructions[]': ['Morning with food']
    }, follow_redirects=True)
    assert res_save_enc.status_code == 200

    saved_enc = Encounter.query.get(draft_enc.id)
    assert saved_enc.status == 'completed'
    assert saved_enc.hopi == 'Severe intermittent headache for 4 days'
    assert len(saved_enc.diagnoses) == 1
    assert saved_enc.diagnoses[0].diagnosis_text == 'Essential Hypertension'
    assert len(saved_enc.prescriptions[0].items) == 1

    # 6. Billing: Create Voucher linked to encounter (Requirement 45 & 77)
    res_voucher_page = client.get(f'/billing/vouchers/new?encounter_id={saved_enc.id}')
    assert res_voucher_page.status_code == 200

    res_create_voucher = client.post(f'/billing/vouchers/new?encounter_id={saved_enc.id}', data={
        'item_desc[]': ['Doctor Consultation', 'Blood Pressure Check'],
        'item_qty[]': ['1', '1'],
        'item_price[]': ['10000', '2000'],
        'discount': '1000'
    }, follow_redirects=True)
    assert res_create_voucher.status_code == 200

    voucher = Voucher.query.filter_by(encounter_id=saved_enc.id).first()
    assert voucher is not None
    assert voucher.total == 11000.0
    assert voucher.status == 'unpaid'

    # 7. Record Collection Payment
    res_pay = client.post(f'/billing/vouchers/{voucher.id}', data={
        'amount': '11000',
        'payment_method': 'Cash',
        'reference': 'CASH-RECEIPT-001'
    }, follow_redirects=True)
    assert res_pay.status_code == 200

    reloaded_voucher = Voucher.query.get(voucher.id)
    assert reloaded_voucher.status == 'fully_paid'
    assert reloaded_voucher.total_paid == 11000.0

    # 8. Appointments & linking to encounter
    res_app = client.post('/appointments/new', data={
        'patient_id': str(patient.id),
        'appointment_date': '2026-09-15',
        'appointment_time': '10:30',
        'doctor_id': str(test_users['doctor'].id),
        'reason': 'Hypertension Review Follow-up'
    }, follow_redirects=True)
    assert res_app.status_code == 200

    appointment = Appointment.query.filter_by(patient_id=patient.id).first()
    assert appointment is not None
    assert appointment.status == 'Scheduled'

    # 9. Admin view audit log
    client.get('/logout', follow_redirects=True)
    client.post('/login', data={
        'username': 'test_admin',
        'password': 'admin123'
    }, follow_redirects=True)

    res_audit = client.get('/administration/audit')
    assert res_audit.status_code == 200
    assert b'Patient' in res_audit.data
    assert b'Encounter' in res_audit.data

