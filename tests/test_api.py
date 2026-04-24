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

        entries = Company.query.filter_by(user_id=user.id).all()
        assert len(entries) == 2

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
