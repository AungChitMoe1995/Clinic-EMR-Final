import datetime
from app.helpers import PatientService
from app.models import Patient, PatientPhone

def test_create_patient_myanmar_naming_and_phones(db):
    data = {
        'sir_name': 'U',
        'patient_name': 'Aung Aung',
        'gender': 'Male',
        'date_of_birth': '1990-05-15',
        'phone_number': '09123456789, 09987654321',
        'city_township': 'Kamayut',
        'state_region': 'Yangon'
    }

    patient = PatientService.create_patient(data)
    assert patient.id is not None
    assert patient.sir_name == 'U'
    assert patient.patient_name == 'Aung Aung'
    assert patient.full_name == 'U Aung Aung'
    assert patient.registration_number.startswith('REG-')

    # Phone numbers normalized into separate records (Requirement 19)
    assert len(patient.phones) == 2
    assert patient.phones[0].phone_number == '09123456789'
    assert patient.phones[0].is_primary is True
    assert patient.phones[1].phone_number == '09987654321'
    assert patient.phones[1].is_primary is False

def test_dynamic_age_calculation(db):
    ref_date = datetime.date(2026, 9, 6)
    p = Patient(
        registration_number='TEST-001',
        sir_name='Daw',
        patient_name='Mya Mya',
        gender='Female',
        date_of_birth=datetime.date(1991, 7, 20)
    )
    age = p.get_dynamic_age(ref_date=ref_date)
    assert age['years'] == 35
    assert age['months'] == 1
    assert age['days'] == 17
    assert '35 Years 1 Month 17 Days' in age['formatted']

def test_calculate_dob_from_age(db):
    ref_date = datetime.date(2026, 9, 6)
    # 20 years, 0 months, 0 days
    dob = PatientService.calculate_dob_from_age(years=20, months=0, days=0, ref_date=ref_date)
    assert dob.year == 2006
    assert dob.month == 9
    assert dob.day == 6

def test_patient_search_by_phone_and_reg(db):
    p1 = PatientService.create_patient({
        'sir_name': 'Ko',
        'patient_name': 'Kyaw Kyaw',
        'gender': 'Male',
        'phone_number': '09111222333'
    })
    p2 = PatientService.create_patient({
        'sir_name': 'Ma',
        'patient_name': 'Hla Hla',
        'gender': 'Female',
        'phone_number': '09444555666, 09777888999'
    })

    # Search by secondary phone
    search_res = PatientService.search_patients(query_str='09777888999')
    assert search_res.total == 1
    assert search_res.items[0].patient_name == 'Hla Hla'

    # Search by name
    search_name = PatientService.search_patients(query_str='Kyaw')
    assert search_name.total == 1
    assert search_name.items[0].id == p1.id

