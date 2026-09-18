import os
from datetime import datetime, date
from app import create_app
from app.extensions import db
from app.models import (
    Account, User, Doctor, RegistrationNumberSetting, SirNameSetting,
    PatientFieldSetting, SystemSetting, InventoryCategory,
    InventoryItem, InventoryTransaction
)

def seed_database():
    app = create_app('development')
    with app.app_context():
        # Create tables
        db.create_all()
        print("Database tables initialized.")

        # 1. System Settings
        default_state = SystemSetting.query.filter_by(setting_key='default_state_region').first()
        if not default_state:
            db.session.add(SystemSetting(setting_key='default_state_region', setting_value='Yangon'))
            print("Seeded default_state_region: Yangon")

        # 2. Registration Number Settings
        reg_setting = RegistrationNumberSetting.query.first()
        if not reg_setting:
            reg_setting = RegistrationNumberSetting(
                format_pattern='REG-{YYYY}-{NUMBER}',
                increment_amount=1,
                next_number=101,
                padding=6
            )
            db.session.add(reg_setting)
            print("Seeded Registration Number Setting (starts at 101, padding 6)")

        # 3. Default Myanmar Sir Names & Gender Mappings (Requirement 13)
        default_sir_names = [
            ('U', 'Male', 1),
            ('Ko', 'Male', 2),
            ('Ma', 'Female', 3),
            ('Daw', 'Female', 4),
            ('Ashin', 'Male', 5),
            ('Sayarlay', 'Female', 6),
            ('Dr', 'Male', 7),
            ('Prof', 'Male', 8),
            ('Baby', 'Male', 9),
        ]
        for title, gender, order in default_sir_names:
            sn = SirNameSetting.query.filter_by(title=title).first()
            if not sn:
                db.session.add(SirNameSetting(title=title, default_gender=gender, is_default=True, display_order=order))
        print("Seeded Myanmar Sir Names and gender mappings.")

        # 4. Mandatory / Default Patient Field Settings (Requirement 16)
        default_fields = [
            ('sir_name', 'Sir Name', True),
            ('patient_name', 'Patient Name', True),
            ('gender', 'Gender', True),
            ('phone_number', 'Phone Number', True),
            ('date_of_birth', 'Date of Birth', False),
            ('marital_status', 'Marital Status', False),
            ('occupation', 'Occupation', False),
            ('blood_group', 'Blood Group', False),
            ('guardian_name', 'Guardian Name', False),
            ('nrc_number', 'NRC Number', False),
            ('email', 'Email', False),
            ('address', 'Address', False),
            ('city_township', 'City / Township', False),
            ('state_region', 'State / Region', False),
            ('patient_summary', 'Patient Summary', False),
            ('notes', 'Administrative Notes', False),
        ]
        for fname, label, is_req in default_fields:
            pf = PatientFieldSetting.query.filter_by(field_name=fname).first()
            if not pf:
                db.session.add(PatientFieldSetting(field_name=fname, label=label, is_required=is_req, is_visible=True))
        print("Seeded patient field requirement settings.")

        # 5. Default Users & Clinic Accounts
        # Clinic Account (One-Account-One-Clinic)
        acc = Account.query.filter_by(phone_number='09123456789').first()
        if not acc:
            acc = Account(
                phone_number='09123456789',
                clinic_name='Central Clinic (Yangon)',
                doctor_name='Dr. Aung Kyaw',
                is_active=True
            )
            acc.set_password('password123')
            db.session.add(acc)
            print("Seeded Default Clinic Account: Phone=09123456789 / Password=password123")

        # Admin User
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin', role='ADMINISTRATOR', is_active=True)
            admin.set_password('admin123')
            db.session.add(admin)
            print("Seeded Administrator: admin / admin123")

        # Receptionist
        reception = User.query.filter_by(username='reception').first()
        if not reception:
            reception = User(username='reception', role='RECEPTIONIST', is_active=True)
            reception.set_password('reception123')
            db.session.add(reception)
            print("Seeded Receptionist: reception / reception123")

        # Doctor User & Doctor Profile
        doc_user = User.query.filter_by(username='dr.aung').first()
        if not doc_user:
            doc_user = User(username='dr.aung', role='DOCTOR', is_active=True)
            doc_user.set_password('doctor123')
            db.session.add(doc_user)
            db.session.flush()

            doctor = Doctor(
                user_id=doc_user.id,
                name='Aung Kyaw',
                title='Dr.',
                specialty='General Medicine',
                phone='09123456789',
                email='dr.aung@clinic.com',
                is_active=True
            )
            db.session.add(doctor)
            print("Seeded Doctor User: dr.aung / doctor123 and Doctor Profile: Dr. Aung Kyaw")

        # 6. Sample Inventory Categories and Items
        cat_oral = InventoryCategory.query.filter_by(name='Oral Solid').first()
        if not cat_oral:
            cat_oral = InventoryCategory(name='Oral Solid', description='Tablets and capsules')
            db.session.add(cat_oral)
            db.session.flush()

        sample_items = [
            ('Paracetamol 500mg', 'Paracetamol', 'Biogesic', 'Tablet', 100.0, 30.0, 50.0, 20.0),
            ('Amoxicillin 500mg', 'Amoxicillin', 'Amoxil', 'Capsule', 50.0, 150.0, 250.0, 15.0),
            ('Omeprazole 20mg', 'Omeprazole', 'Omez', 'Capsule', 80.0, 120.0, 200.0, 20.0),
            ('Cetirizine 10mg', 'Cetirizine', 'Zyrtec', 'Tablet', 60.0, 80.0, 120.0, 10.0),
        ]
        for iname, gen, brand, unit, qty, buy, sell, reorder in sample_items:
            item = InventoryItem.query.filter_by(item_name=iname).first()
            if not item:
                item = InventoryItem(
                    item_name=iname,
                    generic_name=gen,
                    brand=brand,
                    category_id=cat_oral.id,
                    unit=unit,
                    quantity=qty,
                    purchase_price=buy,
                    selling_price=sell,
                    reorder_level=reorder,
                    is_active=True
                )
                db.session.add(item)
                db.session.flush()
                txn = InventoryTransaction(
                    item_id=item.id,
                    transaction_type='IN',
                    quantity=qty,
                    balance_after=qty,
                    reference='Initial Stock',
                    notes='Seed initialization'
                )
                db.session.add(txn)
        print("Seeded sample pharmacy inventory items.")

        db.session.commit()
        print("Database seeding completed successfully!")

if __name__ == '__main__':
    seed_database()

