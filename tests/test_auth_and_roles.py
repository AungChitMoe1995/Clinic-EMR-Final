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

def test_role_authorization_boundaries(client, test_users):
    # Receptionist attempts to access administration
    with client.session_transaction() as sess:
        sess['_user_id'] = test_users['reception'].id
        sess['user_role'] = 'RECEPTIONIST'

    resp = client.get('/administration', follow_redirects=True)
    assert resp.status_code == 200
    assert b'You do not have permission to access this resource' in resp.data

    # Admin accesses administration
    with client.session_transaction() as sess:
        sess['_user_id'] = test_users['admin'].id
        sess['user_role'] = 'ADMINISTRATOR'

    admin_resp = client.get('/administration', follow_redirects=True)
    assert admin_resp.status_code == 200
    assert b'User Management' in admin_resp.data or b'Administration' in admin_resp.data

