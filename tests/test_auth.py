import re
import pytest
import pyotp
from app.models import User
from app import db as _db


def _csrf(client, path):
    res = client.get(path)
    m = re.search(r'name="csrf_token" value="([^"]+)"', res.data.decode())
    return m.group(1) if m else ''


class TestRegister:
    def test_register_success(self, client, db):
        token = _csrf(client, '/register')
        res = client.post('/register', data={
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'SecurePass1',
            'password_confirm': 'SecurePass1',
            'csrf_token': token,
        }, follow_redirects=True)
        assert res.status_code == 200
        assert User.query.filter_by(username='newuser').first() is not None

    def test_register_duplicate_username(self, client, db, user):
        token = _csrf(client, '/register')
        res = client.post('/register', data={
            'username': 'testuser',
            'email': 'other@example.com',
            'password': 'SecurePass1',
            'password_confirm': 'SecurePass1',
            'csrf_token': token,
        })
        assert b'Username already taken' in res.data

    def test_register_password_too_short(self, client, db):
        token = _csrf(client, '/register')
        res = client.post('/register', data={
            'username': 'shortpw',
            'email': 'shortpw@example.com',
            'password': 'short',
            'password_confirm': 'short',
            'csrf_token': token,
        })
        assert res.status_code == 200
        assert User.query.filter_by(username='shortpw').first() is None


class TestLogin:
    def test_login_success(self, client, db, user):
        token = _csrf(client, '/login')
        res = client.post('/login', data={
            'username': 'testuser',
            'password': 'password123',
            'csrf_token': token,
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b'Dashboard' in res.data

    def test_login_wrong_password(self, client, db, user):
        token = _csrf(client, '/login')
        res = client.post('/login', data={
            'username': 'testuser',
            'password': 'wrong',
            'csrf_token': token,
        })
        assert res.status_code == 401
        assert b'Invalid username or password' in res.data

    def test_login_unknown_user(self, client, db):
        token = _csrf(client, '/login')
        res = client.post('/login', data={
            'username': 'nobody',
            'password': 'password123',
            'csrf_token': token,
        })
        assert res.status_code == 401


class TestLogout:
    def test_logout_redirects(self, client, db, user):
        token = _csrf(client, '/login')
        client.post('/login', data={
            'username': 'testuser',
            'password': 'password123',
            'csrf_token': token,
        })
        res = client.get('/logout', follow_redirects=True)
        assert b'Sign in' in res.data


class TestProfilePasswordChange:
    def test_password_change_success(self, client, db, user, logged_in_client):
        token = _csrf(logged_in_client, '/profile')
        res = logged_in_client.post('/profile', data={
            'email': 'test@example.com',
            'current_password': 'password123',
            'new_password': 'NewSecurePass9',
            'new_password_confirm': 'NewSecurePass9',
            'csrf_token': token,
        }, follow_redirects=True)
        assert res.status_code == 200
        u = User.query.filter_by(username='testuser').first()
        assert u.check_password('NewSecurePass9')

    def test_password_change_wrong_current(self, client, db, user, logged_in_client):
        token = _csrf(logged_in_client, '/profile')
        res = logged_in_client.post('/profile', data={
            'email': 'test@example.com',
            'current_password': 'wrongcurrent',
            'new_password': 'NewSecurePass9',
            'new_password_confirm': 'NewSecurePass9',
            'csrf_token': token,
        })
        assert b'Current password is incorrect' in res.data


class TestPasswordChangeSessionRegeneration:
    def test_password_change_regenerates_session(self, client, db, user, logged_in_client):
        """After a password change, the user should remain logged in (session regenerated)."""
        # Arrange — verify the user is currently logged in
        res = logged_in_client.get('/dashboard')
        assert res.status_code == 200

        # Act — change password
        token = _csrf(logged_in_client, '/profile')
        res = logged_in_client.post('/profile', data={
            'email': 'test@example.com',
            'current_password': 'password123',
            'new_password': 'BrandNewPass99',
            'new_password_confirm': 'BrandNewPass99',
            'csrf_token': token,
        }, follow_redirects=True)

        # Assert — still logged in (session regenerated, not cleared)
        assert res.status_code == 200
        dashboard = logged_in_client.get('/dashboard')
        assert dashboard.status_code == 200

        # And the new password is saved
        u = User.query.filter_by(username='testuser').first()
        assert u.check_password('BrandNewPass99')


class TestTwoFactorLogin:
    def _enable_2fa_for_user(self, user):
        """Helper: enable 2FA on the user object directly."""
        secret = pyotp.random_base32()
        user.two_factor_secret = secret
        user.two_factor_enabled = True
        _db.session.commit()
        return secret

    def test_login_with_2fa_enabled_redirects_to_2fa_page(self, client, db, user):
        # Arrange
        self._enable_2fa_for_user(user)

        # Act
        token = _csrf(client, '/login')
        res = client.post('/login', data={
            'username': 'testuser',
            'password': 'password123',
            'csrf_token': token,
        })

        # Assert — redirect to 2FA step, not dashboard
        assert res.status_code in (301, 302)
        assert '/login/2fa' in res.headers.get('Location', '')

    def test_login_2fa_valid_code_succeeds(self, client, db, user):
        # Arrange
        secret = self._enable_2fa_for_user(user)

        token = _csrf(client, '/login')
        client.post('/login', data={
            'username': 'testuser',
            'password': 'password123',
            'csrf_token': token,
        })

        # Act — submit valid TOTP code
        totp_token = _csrf(client, '/login/2fa')
        code = pyotp.TOTP(secret).now()
        res = client.post('/login/2fa', data={
            'code': code,
            'csrf_token': totp_token,
        }, follow_redirects=True)

        # Assert — logged in and on dashboard
        assert res.status_code == 200
        assert b'Dashboard' in res.data

    def test_login_2fa_invalid_code_fails(self, client, db, user):
        # Arrange
        self._enable_2fa_for_user(user)

        token = _csrf(client, '/login')
        client.post('/login', data={
            'username': 'testuser',
            'password': 'password123',
            'csrf_token': token,
        })

        # Act — submit wrong TOTP code
        totp_token = _csrf(client, '/login/2fa')
        res = client.post('/login/2fa', data={
            'code': '000000',
            'csrf_token': totp_token,
        })

        # Assert — rejected
        assert res.status_code == 401
        assert b'Invalid or expired code' in res.data

    def test_login_2fa_no_pending_session_redirects_to_login(self, client, db):
        # Act — access /login/2fa without going through step 1
        res = client.get('/login/2fa', follow_redirects=False)

        # Assert — redirected to login
        assert res.status_code in (301, 302)
        assert '/login' in res.headers.get('Location', '')

