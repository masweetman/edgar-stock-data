import pytest
from unittest.mock import MagicMock, patch

from app import create_app, db as _db
from app.models import User, UserConfig


@pytest.fixture(scope='session')
def app():
    app = create_app('testing')
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture(scope='function')
def db(app):
    with app.app_context():
        yield _db
        _db.session.remove()
        # Truncate all tables between tests
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()
        # Reset rate limit counters so tests don't bleed into each other
        from app import limiter as _limiter
        try:
            _limiter.reset()
        except Exception:
            pass


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user(db):
    u = User(username='testuser', email='test@example.com')
    u.set_password('password123')
    db.session.add(u)
    db.session.commit()
    cfg = UserConfig(user_id=u.id, sec_email='test@example.com')
    cfg.tickers = ['AAPL', 'MSFT']
    cfg.years = ['2022', '2023']
    db.session.add(cfg)
    db.session.commit()
    return u


@pytest.fixture
def logged_in_client(client, user):
    client.post('/login', data={'username': 'testuser', 'password': 'password123',
                                'csrf_token': _get_csrf(client, '/login')})
    return client


def _get_csrf(client, path):
    res = client.get(path)
    import re
    m = re.search(r'name="csrf_token" value="([^"]+)"', res.data.decode())
    return m.group(1) if m else ''


@pytest.fixture
def mock_fetch_data():
    with patch('app.views.fetch_data') as mock:
        mock.return_value = {
            'AAPL': {'cik': '0000320193', 'eps_avg': 6.11, 'bvps': 3.85, 'div': 0.96, 'div_date': '2023-12-31', 'error': None},
            'MSFT': {'cik': '0000789019', 'eps_avg': 9.72, 'bvps': 24.10, 'div': 2.72, 'div_date': '2023-12-31', 'error': None},
        }
        yield mock
