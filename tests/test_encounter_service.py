from datetime import datetime
from app.helpers import PatientService, EncounterService
from app.models import (
    Patient, Encounter, EncounterHistory, EncounterVital,
    EncounterDiagnosis, Prescription, PrescriptionItem
)

def test_doctor_auto_assignment(db, test_users):
    patient = PatientService.create_patient({
        'sir_name': 'U',
        'patient_name': 'Aung San',
        'gender': 'Male',
        'phone_number': '09123456789'
    })

    # Logged-in doctor creates encounter
    doc_id = EncounterService.resolve_doctor_for_user(test_users['doctor_user'])
    assert doc_id == test_users['doctor'].id

    # Receptionist creates encounter without selecting doctor -> None
    rec_doc_id = EncounterService.resolve_doctor_for_user(test_users['reception'], selected_doctor_id=None)
    assert rec_doc_id is None

    # Receptionist explicitly selects doctor -> selected doctor ID
    rec_doc_id_selected = EncounterService.resolve_doctor_for_user(test_users['reception'], selected_doctor_id=test_users['doctor'].id)
    assert rec_doc_id_selected == test_users['doctor'].id

def test_empty_encounter_discard_rule(db, test_users):
    patient = PatientService.create_patient({
        'sir_name': 'Daw',
        'patient_name': 'Khin Khin',
        'gender': 'Female',
        'phone_number': '09222333444'
    })

    # Create draft encounter
    draft_enc = Encounter(patient_id=patient.id, status='draft')
    db.session.add(draft_enc)
    db.session.commit()
    draft_id = draft_enc.id

    # No meaningful data entered -> discard
    discarded = EncounterService.discard_encounter_if_empty(draft_id)
    assert discarded is True
    assert Encounter.query.get(draft_id) is None

    # Verify patient remains registered and intact (Requirement 25)
    assert Patient.query.get(patient.id) is not None

def test_history_copying_and_independence(db, test_users):
    patient = PatientService.create_patient({
        'sir_name': 'U',
        'patient_name': 'Min Thu',
        'gender': 'Male',
        'phone_number': '09333444555'
    })

    # Encounter 1: Doctor records HOPI and History
    enc1 = Encounter(
        patient_id=patient.id,
        doctor_id=test_users['doctor'].id,
        status='completed',
        hopi='Cough and fever for 3 days',
        examination='Chest: Bilateral wheeze'
    )
    db.session.add(enc1)
    db.session.flush()

    hist1 = EncounterHistory(
        encounter_id=enc1.id,
        pmh='Hypertension (10 yrs)',
        psh='Appendectomy (2015)',
        drug_history='Amlodipine 5mg OD',
        allergy_history='Penicillin'
    )
    db.session.add(hist1)
    db.session.commit()

    # Now create Encounter 2 for the same patient
    # History copying (Requirement 39): Copy past history, NEVER copy HOPI
    copied_hist = EncounterService.copy_previous_history(patient.id)
    assert copied_hist['pmh'] == 'Hypertension (10 yrs)'
    assert copied_hist['psh'] == 'Appendectomy (2015)'
    assert copied_hist['drug_history'] == 'Amlodipine 5mg OD'
    assert copied_hist['allergy_history'] == 'Penicillin'

    # Verify HOPI is NOT in copied history
    assert 'hopi' not in copied_hist

    enc2 = Encounter(
        patient_id=patient.id,
        doctor_id=test_users['doctor'].id,
        status='completed',
        hopi='Follow up visit for blood pressure check',
        examination='BP normal, chest clear'
    )
    db.session.add(enc2)
    db.session.flush()

    hist2 = EncounterHistory(
        encounter_id=enc2.id,
        pmh='Hypertension (10 yrs), newly diagnosed Type 2 DM', # Modified in encounter 2
        psh=copied_hist['psh'],
        drug_history='Amlodipine 5mg OD, Metformin 500mg BD', # Modified in encounter 2
        allergy_history=copied_hist['allergy_history']
    )
    db.session.add(hist2)
    db.session.commit()

    # History independence: Encounter 1 records must remain unchanged (Requirement 40 & 58)
    reloaded_enc1 = Encounter.query.get(enc1.id)
    reloaded_enc2 = Encounter.query.get(enc2.id)

    assert reloaded_enc1.hopi == 'Cough and fever for 3 days'
    assert reloaded_enc2.hopi == 'Follow up visit for blood pressure check'
    assert reloaded_enc1.history.pmh == 'Hypertension (10 yrs)'
    assert reloaded_enc2.history.pmh == 'Hypertension (10 yrs), newly diagnosed Type 2 DM'
    assert reloaded_enc1.history.drug_history == 'Amlodipine 5mg OD'
    assert reloaded_enc2.history.drug_history == 'Amlodipine 5mg OD, Metformin 500mg BD'

def test_prescription_independence(db, test_users):
    patient = PatientService.create_patient({
        'sir_name': 'Ma',
        'patient_name': 'Su Su',
        'gender': 'Female',
        'phone_number': '09555666777'
    })

    # Encounter 1 with prescription
    enc1 = Encounter(patient_id=patient.id, status='completed')
    db.session.add(enc1)
    db.session.flush()

    rx1 = Prescription(encounter_id=enc1.id, patient_id=patient.id)
    rx1.items.append(PrescriptionItem(medicine_name='Amoxicillin 500mg', dose='500mg', quantity=20))
    db.session.add(rx1)
    db.session.commit()

    # Encounter 2 has no prescriptions by default (Requirement 42)
    enc2 = Encounter(patient_id=patient.id, status='completed')
    db.session.add(enc2)
    db.session.commit()

    assert len(enc2.prescriptions) == 0
    assert len(enc1.prescriptions) == 1
