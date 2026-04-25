import json
import re
import pytest
import pyotp

from app.models import Company, User


def _csrf(client, path):
    res = client.get(path)
    m = re.search(r'name="csrf_token" value="([^"]+)"', res.data.decode())
    return m.group(1) if m else ''


class TestApiFetch:
    def test_fetch_unauthenticated(self, client, db):
        res = client.post('/api/fetch')
        assert res.status_code == 401
        assert res.json['success'] is False

    def test_fetch_success(self, client, db, user, logged_in_client, mock_fetch_data):
        res = logged_in_client.post('/api/fetch')
        assert res.status_code == 200
        data = res.json
        assert data['success'] is True
        assert len(data['data']) == 2
        tickers = {e['ticker'] for e in data['data']}
        assert 'AAPL' in tickers and 'MSFT' in tickers

        entries = Company.query.all()
        assert len(entries) == 2

    def test_fetch_populates_buffett_fields(self, client, db, user, logged_in_client, mock_fetch_data):
        res = logged_in_client.post('/api/fetch')
        assert res.status_code == 200
        entry_dicts = res.json['data']
        for e in entry_dicts:
            # intrinsic_value and owner_earnings should be computed from the rich mock data
            assert e['intrinsic_value'] is not None, f"{e['ticker']} intrinsic_value missing"
            assert e['owner_earnings'] is not None, f"{e['ticker']} owner_earnings missing"
            assert e['quality_score'] is not None, f"{e['ticker']} quality_score missing"

    def test_fetch_with_minimal_edgar_data_does_not_crash(self, client, db, user, logged_in_client):
        """When EDGAR returns no Buffett fields, the row is still saved with nulls."""
        minimal = {
            'AAPL': {
                'cik': '0000320193', 'eps_avg': 6.11, 'bvps': 3.85,
                'div': 0.96, 'div_date': '2023-12-31', 'error': None,
                'net_income_history': {}, 'da_history': {}, 'capex_history': {},
                'revenue_history': {}, 'operating_income_history': {},
                'long_term_debt': None, 'equity': None, 'shares_outstanding': None,
            },
        }
        from unittest.mock import patch
        with patch('app.views.fetch_data', return_value=minimal):
            res = logged_in_client.post('/api/fetch')
        assert res.status_code == 200
        assert res.json['success'] is True
        entry = Company.query.filter_by(ticker='AAPL').first()
        assert entry is not None
        assert entry.intrinsic_value is None  # gracefully None, no crash

    def test_fetch_no_config(self, client, db):
        # Register a user without config
        token = _csrf(client, '/register')
        client.post('/register', data={
            'username': 'nocfg',
            'email': 'nocfg@example.com',
            'password': 'password123',
            'password_confirm': 'password123',
            'csrf_token': token,
        })
        res = client.post('/api/fetch')
        assert res.status_code == 400
        assert res.json['success'] is False

    def test_fetch_service_error(self, client, db, user, logged_in_client):
        from unittest.mock import patch
        with patch('app.views.fetch_data', side_effect=Exception('SEC down')):
            res = logged_in_client.post('/api/fetch')
        assert res.status_code == 502
        assert res.json['success'] is False


class TestApi2FA:
    def test_setup_unauthenticated(self, client, db):
        res = client.get('/api/2fa/setup')
        assert res.status_code == 401

    def test_setup_returns_qr_and_secret(self, client, db, user, logged_in_client):
        res = logged_in_client.get('/api/2fa/setup')
        assert res.status_code == 200
        data = res.json
        assert data['success'] is True
        assert 'secret' in data
        assert data['qr_image'].startswith('data:image/png;base64,')

    def test_enable_and_disable_2fa(self, client, db, user, logged_in_client):
        # Setup
        setup_res = logged_in_client.get('/api/2fa/setup')
        secret = setup_res.json['secret']
        code = pyotp.TOTP(secret).now()

        # Enable
        enable_res = logged_in_client.post('/api/2fa/enable',
            data=json.dumps({'password': 'password123', 'code': code}),
            content_type='application/json')
        assert enable_res.json['success'] is True

        u = User.query.filter_by(username='testuser').first()
        assert u.two_factor_enabled is True

        # Disable
        code2 = pyotp.TOTP(secret).now()
        disable_res = logged_in_client.post('/api/2fa/disable',
            data=json.dumps({'password': 'password123', 'code': code2}),
            content_type='application/json')
        assert disable_res.json['success'] is True
        u = User.query.filter_by(username='testuser').first()
        assert u.two_factor_enabled is False

    def test_enable_bad_password(self, client, db, user, logged_in_client):
        logged_in_client.get('/api/2fa/setup')
        res = logged_in_client.post('/api/2fa/enable',
            data=json.dumps({'password': 'wrong', 'code': '123456'}),
            content_type='application/json')
        assert res.status_code == 400
        assert res.json['success'] is False

    def test_enable_bad_code(self, client, db, user, logged_in_client):
        logged_in_client.get('/api/2fa/setup')
        res = logged_in_client.post('/api/2fa/enable',
            data=json.dumps({'password': 'password123', 'code': '000000'}),
            content_type='application/json')
        assert res.status_code == 400
        assert res.json['success'] is False
