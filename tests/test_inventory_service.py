import pytest
from app.helpers import InventoryService, PatientService
from app.models import InventoryItem, InventoryTransaction, Encounter, Prescription, PrescriptionItem

def test_inventory_movements_and_balance(db):
    item = InventoryItem(
        item_name='Amoxicillin 250mg',
        quantity=50.0,
        reorder_level=20.0
    )
    db.session.add(item)
    db.session.commit()

    # Stock IN
    txn_in = InventoryService.record_stock_transaction(
        item_id=item.id,
        transaction_type='IN',
        quantity=30.0,
        reference='PO-2026-001'
    )
    assert item.quantity == 80.0
    assert txn_in.balance_after == 80.0

    # Stock OUT
    txn_out = InventoryService.record_stock_transaction(
        item_id=item.id,
        transaction_type='OUT',
        quantity=25.0,
        reference='DISP-001'
    )
    assert item.quantity == 55.0
    assert txn_out.balance_after == 55.0

    # Stock Adjustment (physical inventory audit override)
    txn_adj = InventoryService.record_stock_transaction(
        item_id=item.id,
        transaction_type='ADJUSTMENT',
        quantity=50.0,
        notes='Monthly physical audit'
    )
    assert item.quantity == 50.0
    assert txn_adj.balance_after == 50.0

def test_insufficient_stock_error(db):
    item = InventoryItem(item_name='Insulin Glargine', quantity=5.0)
    db.session.add(item)
    db.session.commit()

    with pytest.raises(ValueError, match="Insufficient stock"):
        InventoryService.record_stock_transaction(
            item_id=item.id,
            transaction_type='OUT',
            quantity=10.0
        )

def test_prescription_does_not_auto_deduct_inventory(db):
    """Requirement 52: Do NOT automatically deduct inventory merely because a doctor typed a prescription."""
    item = InventoryItem(item_name='Paracetamol 500mg', quantity=100.0)
    db.session.add(item)
    db.session.commit()

    patient = PatientService.create_patient({
        'sir_name': 'Ko',
        'patient_name': 'Zayar',
        'gender': 'Male',
        'phone_number': '091234567'
    })
    encounter = Encounter(patient_id=patient.id, status='completed')
    db.session.add(encounter)
    db.session.flush()

    rx = Prescription(encounter_id=encounter.id, patient_id=patient.id)
    rx_item = PrescriptionItem(
        medicine_name='Paracetamol 500mg',
        inventory_item_id=item.id,
        quantity=20.0
    )
    rx.items.append(rx_item)
    db.session.add(rx)
    db.session.commit()

    # Stock quantity must remain intact
    reloaded_item = InventoryItem.query.get(item.id)
    assert reloaded_item.quantity == 100.0

