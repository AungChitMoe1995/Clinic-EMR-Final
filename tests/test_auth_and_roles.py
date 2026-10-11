def test_login_and_logout(client, test_users):
    resp = client.post('/login', data={
        'username': 'test_admin',
        'password': 'admin123'
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'Patients' in resp.data

    logout_resp = client.get('/logout', follow_redirects=True)
    assert logout_resp.status_code == 200
    assert b'Sign In' in logout_resp.data


def test_full_access_for_authenticated_users(client, test_users):
    # Under simplified one-account-one-clinic model, all authenticated users have full access
    with client.session_transaction() as sess:
        sess['_user_id'] = test_users['reception'].id
        sess['user_role'] = 'RECEPTIONIST'

    resp = client.get('/administration', follow_redirects=True)
    assert resp.status_code == 200
    assert b'Administration' in resp.data or b'User Management' in resp.data

def test_account_phone_login_and_plain_text(client, db):
    from app.models import Account
    # Test plain text password support (for direct manual phpMyAdmin entry)
    acc = Account(
        phone_number='09987654321',
        clinic_name='My Test Clinic',
        doctor_name='Dr. Test',
        password_hash='plainpassword123'
    )
    db.session.add(acc)
    db.session.commit()

    resp = client.post('/login', data={
        'username': '09987654321',
        'password': 'plainpassword123'
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'Patients' in resp.data


