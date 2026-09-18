from app.helpers import PatientService, BillingService
from app.models import Encounter, Voucher

def test_voucher_creation_and_calculations(db):
    patient = PatientService.create_patient({
        'sir_name': 'U',
        'patient_name': 'Hla Maung',
        'gender': 'Male',
        'phone_number': '0912345678'
    })
    encounter = Encounter(patient_id=patient.id, status='completed')
    db.session.add(encounter)
    db.session.commit()

    items_data = [
        {'description': 'Consultation Fee', 'quantity': 1, 'unit_price': 10000},
        {'description': 'Blood Glucose Test', 'quantity': 1, 'unit_price': 5000},
        {'description': 'Paracetamol Strip', 'quantity': 2, 'unit_price': 1500}
    ]

    voucher = BillingService.create_voucher(
        encounter_id=encounter.id,
        items_data=items_data,
        discount=1000,
        notes='Test discount applied'
    )

    assert voucher.subtotal == 18000.0
    assert voucher.discount == 1000.0
    assert voucher.total == 17000.0
    assert voucher.status == 'unpaid'
    assert voucher.patient_id == patient.id
    assert voucher.balance_due == 17000.0

def test_multiple_payments_and_status_transitions(db):
    patient = PatientService.create_patient({
        'sir_name': 'Daw',
        'patient_name': 'Tin Tin',
        'gender': 'Female',
        'phone_number': '0987654321'
    })
    encounter = Encounter(patient_id=patient.id, status='completed')
    db.session.add(encounter)
    db.session.commit()

    voucher = BillingService.create_voucher(
        encounter_id=encounter.id,
        items_data=[{'description': 'Minor Procedure', 'quantity': 1, 'unit_price': 50000}],
        discount=0
    )
    assert voucher.status == 'unpaid'

    # Payment 1: Partial payment of 20,000 MMK
    p1 = BillingService.record_payment(
        voucher_id=voucher.id,
        amount=20000,
        payment_method='Cash',
        notes='Advance cash deposit'
    )
    reloaded_voucher = Voucher.query.get(voucher.id)
    assert reloaded_voucher.total_paid == 20000.0
    assert reloaded_voucher.balance_due == 30000.0
    assert reloaded_voucher.status == 'partially_paid'

    # Payment 2: Full settlement of remaining 30,000 MMK
    p2 = BillingService.record_payment(
        voucher_id=voucher.id,
        amount=30000,
        payment_method='Mobile Payment',
        reference='KBZPAY-REF-998877'
    )
    reloaded_voucher = Voucher.query.get(voucher.id)
    assert reloaded_voucher.total_paid == 50000.0
    assert reloaded_voucher.balance_due == 0.0
    assert reloaded_voucher.status == 'fully_paid'
    assert len(reloaded_voucher.payments) == 2

    # Patient consolidated billing
    summary = BillingService.get_patient_billing_summary(patient.id)
    assert summary['total_billed'] == 50000.0
    assert summary['total_paid'] == 50000.0
    assert summary['total_outstanding'] == 0.0

