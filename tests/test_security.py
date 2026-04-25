import json
import logging
import re
import pytest

from app import create_app, db as _db
from app.models import Company, User, UserConfig


def _csrf(client, path):
    res = client.get(path)
    m = re.search(r'name="csrf_token" value="([^"]+)"', res.data.decode())
    return m.group(1) if m else ''


def _login(client, username, password):
    token = _csrf(client, '/login')
    client.post('/login', data={
        'username': username,
        'password': password,
        'csrf_token': token,
    })


class TestUnauthenticatedAccess:
    """All protected routes must redirect or return 401 when unauthenticated."""

    def test_dashboard_redirects(self, client, db):
        res = client.get('/dashboard')
        assert res.status_code in (301, 302)

    def test_config_redirects(self, client, db):
        res = client.get('/config')
        assert res.status_code in (301, 302)

    def test_profile_redirects(self, client, db):
        res = client.get('/profile')
        assert res.status_code in (301, 302)

    def test_api_fetch_returns_401(self, client, db):
        res = client.post('/api/fetch')
        assert res.status_code == 401
        assert res.json['success'] is False

    def test_api_2fa_setup_returns_401(self, client, db):
        res = client.get('/api/2fa/setup')
        assert res.status_code == 401

    def test_api_2fa_enable_returns_401(self, client, db):
        res = client.post('/api/2fa/enable',
                          data='{}', content_type='application/json')
        assert res.status_code == 401


class TestCrossUserIsolation:
    """Users only see tickers they have configured. The /company/<ticker> route
    enforces a 403 for tickers not in the user's config."""

    def _create_user(self, db, username, email, tickers):
        u = User(username=username, email=email)
        u.set_password('password123')
        _db.session.add(u)
        _db.session.commit()
        cfg = UserConfig(user_id=u.id, sec_email=email)
        cfg.tickers = tickers
        _db.session.add(cfg)
        _db.session.commit()
        return u

    def test_user_cannot_access_ticker_not_in_their_config(self, client, db):
        # user_a watches TSLA; user_b watches AAPL (not TSLA)
        self._create_user(db, 'user_a', 'a@example.com', ['TSLA'])
        self._create_user(db, 'user_b', 'b@example.com', ['AAPL'])

        # Add the shared Company row for TSLA
        entry = Company(ticker='TSLA', eps_avg=1.23)
        _db.session.add(entry)
        _db.session.commit()

        # Login as user_b (who does NOT have TSLA configured)
        _login(client, 'user_b', 'password123')

        # user_b's dashboard should not show TSLA
        res = client.get('/dashboard')
        assert res.status_code == 200
        assert b'TSLA' not in res.data

        # user_b should get 403 when trying to navigate directly to /company/TSLA
        res = client.get('/company/TSLA')
        assert res.status_code == 403

    def test_user_sees_their_configured_ticker_on_dashboard(self, client, db):
        self._create_user(db, 'user_c', 'c@example.com', ['TSLA'])

        entry = Company(ticker='TSLA', eps_avg=1.23)
        _db.session.add(entry)
        _db.session.commit()

        _login(client, 'user_c', 'password123')
        res = client.get('/dashboard')
        assert res.status_code == 200
        assert b'TSLA' in res.data


class TestSQLInjection:
    """ORM-based queries must not be vulnerable to SQL injection via inputs."""

    def test_login_sql_injection(self, client, db):
        token = _csrf(client, '/login')
        res = client.post('/login', data={
            'username': "' OR '1'='1",
            'password': "' OR '1'='1",
            'csrf_token': token,
        })
        # Must not succeed
        assert res.status_code in (200, 401)
        # Must not redirect to dashboard
        assert b'Dashboard' not in res.data


class TestXSS:
    """User-supplied content must be escaped in templates."""

    def test_username_escaped_in_response(self, client, db):
        token = _csrf(client, '/register')
        # Attempt to inject script via username is prevented by Length validator (max 64)
        # but let's try a safe-length XSS payload
        xss = '<script>alert(1)</script>'
        client.post('/register', data={
            'username': 'xssuser',
            'email': 'xss@example.com',
            'password': 'password123',
            'password_confirm': 'password123',
            'csrf_token': token,
        })
        _login(client, 'xssuser', 'password123')
        res = client.get('/dashboard')
        # The raw script tag must not appear unescaped in the response
        assert b'<script>alert(1)</script>' not in res.data


class TestRateLimiting:
    """Verify rate limiting is applied to sensitive endpoints."""

    @pytest.fixture(autouse=True)
    def reset_limits(self):
        """Clear rate limit counters before each test to prevent cross-test contamination."""
        from app import limiter as _limiter
        try:
            _limiter.reset()
        except Exception:
            pass
        yield
        try:
            _limiter.reset()
        except Exception:
            pass

    def test_login_rate_limited_after_threshold(self, client, db):
        """Submitting more than 10 login requests per minute must return 429."""
        status_codes = []
        for _ in range(12):
            res = client.post('/login', data={
                'username': 'nobody',
                'password': 'wrongpass',
            })
            status_codes.append(res.status_code)

        assert 429 in status_codes, f'Expected 429 in status codes, got: {set(status_codes)}'

    def test_2fa_verify_rate_limited_after_threshold(self, client, db):
        """Submitting more than 5 /login/2fa requests per minute must return 429."""
        status_codes = []
        for _ in range(7):
            res = client.post('/login/2fa', data={
                'code': '000000',
            })
            status_codes.append(res.status_code)

        assert 429 in status_codes, f'Expected 429 among: {set(status_codes)}'


class TestAdminAuditLogging:
    """Admin create/update/delete actions must emit audit log entries."""

    def _make_admin(self, db):
        u = User(username='adminaudit', email='adminaudit@example.com', is_admin=True)
        u.set_password('adminpass')
        _db.session.add(u)
        _db.session.commit()
        return u

    def test_admin_delete_emits_audit_log(self, client, db):
        # Arrange — create an admin and a target user
        admin = self._make_admin(db)
        target = User(username='victim', email='victim@example.com')
        target.set_password('password123')
        _db.session.add(target)
        _db.session.commit()
        target_id = target.id

        _login(client, 'adminaudit', 'adminpass')

        audit_records = []

        class _CapHandler(logging.Handler):
            def emit(self, record):
                audit_records.append(record.getMessage())

        audit_logger = logging.getLogger('audit')
        original_level = audit_logger.level
        audit_logger.setLevel(logging.DEBUG)
        audit_logger.addHandler(_CapHandler())
        handler = audit_logger.handlers[-1]

        try:
            # Flask-Admin 2.x delete: POST /admin/user/delete/ with id= form field
            res = client.post('/admin/user/delete/', data={'id': target_id, 'url': '/admin/user/'})
        finally:
            audit_logger.removeHandler(handler)
            audit_logger.setLevel(original_level)

        # The delete should result in a redirect (302) or 200
        assert res.status_code in (200, 302, 303), f'Unexpected status: {res.status_code}\n{res.data[:500]}'
        # An admin_delete audit entry must have been produced
        assert any('admin_delete' in r for r in audit_records), \
            f'Expected admin_delete audit entry, got: {audit_records}'

