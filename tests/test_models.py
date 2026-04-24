"""Unit tests for SQLAlchemy models."""
from datetime import datetime, timezone

import pytest

from app.models import StockDataEntry, User, UserConfig
from app import db as _db


class TestUserModel:
    def test_set_and_check_password(self, db):
        # Arrange
        u = User(username='pwtest', email='pw@example.com')

        # Act
        u.set_password('mysecretpassword')

        # Assert
        assert u.password_hash is not None
        assert u.check_password('mysecretpassword') is True
        assert u.check_password('wrongpassword') is False

    def test_password_hash_is_not_plaintext(self, db):
        u = User(username='hashtest', email='hash@example.com')
        u.set_password('plaintext')
        assert 'plaintext' not in u.password_hash

    def test_get_or_create_config_creates_when_missing(self, db):
        # Arrange
        u = User(username='cfgtest', email='cfg@example.com')
        u.set_password('password123')
        _db.session.add(u)
        _db.session.commit()

        # Act
        cfg = u.get_or_create_config()
        _db.session.commit()

        # Assert
        assert cfg is not None
        assert cfg.user_id == u.id

    def test_get_or_create_config_returns_existing(self, db):
        # Arrange
        u = User(username='cfgtest2', email='cfg2@example.com')
        u.set_password('password123')
        _db.session.add(u)
        _db.session.commit()
        existing = UserConfig(user_id=u.id, sec_email='cfg2@example.com')
        _db.session.add(existing)
        _db.session.commit()

        # Act
        cfg = u.get_or_create_config()

        # Assert
        assert cfg.id == existing.id


class TestUserConfigModel:
    def test_tickers_property_roundtrip(self, db):
        # Arrange
        u = User(username='tickertest', email='ticker@example.com')
        u.set_password('password123')
        _db.session.add(u)
        _db.session.commit()
        cfg = UserConfig(user_id=u.id, sec_email='ticker@example.com')
        _db.session.add(cfg)

        # Act
        cfg.tickers = ['AAPL', 'MSFT', 'TSLA']
        _db.session.commit()

        # Assert
        reloaded = _db.session.get(UserConfig, cfg.id)
        assert reloaded.tickers == ['AAPL', 'MSFT', 'TSLA']

    def test_tickers_empty_list(self, db):
        u = User(username='tickerempty', email='tickerempty@example.com')
        u.set_password('password123')
        _db.session.add(u)
        _db.session.commit()
        cfg = UserConfig(user_id=u.id, sec_email='tickerempty@example.com')
        cfg.tickers = []
        _db.session.add(cfg)
        _db.session.commit()

        reloaded = _db.session.get(UserConfig, cfg.id)
        assert reloaded.tickers == []

    def test_years_property_roundtrip(self, db):
        # Arrange
        u = User(username='yeartest', email='year@example.com')
        u.set_password('password123')
        _db.session.add(u)
        _db.session.commit()
        cfg = UserConfig(user_id=u.id, sec_email='year@example.com')
        _db.session.add(cfg)

        # Act
        cfg.years = ['2021', '2022', '2023']
        _db.session.commit()

        # Assert
        reloaded = _db.session.get(UserConfig, cfg.id)
        assert reloaded.years == ['2021', '2022', '2023']


class TestStockDataEntryModel:
    def test_to_dict_contains_required_keys(self, db):
        # Arrange
        u = User(username='dicttest', email='dict@example.com')
        u.set_password('password123')
        _db.session.add(u)
        _db.session.commit()
        entry = StockDataEntry(
            user_id=u.id,
            ticker='AAPL',
            cik='0000320193',
            eps_avg=6.11,
            bvps=3.85,
            div=0.96,
            div_date='2023-12-31',
            fetched_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        _db.session.add(entry)
        _db.session.commit()

        # Act
        d = entry.to_dict()

        # Assert
        assert d['ticker'] == 'AAPL'
        assert d['cik'] == '0000320193'
        assert d['eps_avg'] == 6.11
        assert d['bvps'] == 3.85
        assert d['div'] == 0.96
        assert d['div_date'] == '2023-12-31'
        assert '2024-01-01' in d['fetched_at']

    def test_to_dict_handles_none_fields(self, db):
        u = User(username='nonetest', email='none@example.com')
        u.set_password('password123')
        _db.session.add(u)
        _db.session.commit()
        entry = StockDataEntry(user_id=u.id, ticker='XYZ')
        _db.session.add(entry)
        _db.session.commit()

        d = entry.to_dict()
        assert d['eps_avg'] is None
        assert d['bvps'] is None
        assert d['div'] is None
