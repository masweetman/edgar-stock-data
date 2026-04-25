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
            'AAPL': {
                'cik': '0000320193', 'eps_avg': 6.11, 'bvps': 3.85, 'div': 0.96,
                'div_date': '2023-12-31', 'error': None,
                'net_income_history': {2019: 55256e6, 2020: 57411e6, 2021: 94680e6,
                                       2022: 99803e6, 2023: 96995e6},
                'da_history': {2019: 12547e6, 2020: 11056e6, 2021: 11284e6,
                               2022: 11104e6, 2023: 11519e6},
                'capex_history': {2019: 10495e6, 2020: 7309e6, 2021: 11085e6,
                                  2022: 10708e6, 2023: 10959e6},
                'revenue_history': {2019: 260174e6, 2020: 274515e6, 2021: 365817e6,
                                    2022: 394328e6, 2023: 383285e6},
                'operating_income_history': {2019: 63930e6, 2020: 66288e6, 2021: 108949e6,
                                             2022: 119437e6, 2023: 114301e6},
                'long_term_debt': 95281e6,
                'equity': 62146e6,
                'shares_outstanding': 15550000000,
            },
            'MSFT': {
                'cik': '0000789019', 'eps_avg': 9.72, 'bvps': 24.10, 'div': 2.72,
                'div_date': '2023-12-31', 'error': None,
                'net_income_history': {2019: 39240e6, 2020: 44281e6, 2021: 61271e6,
                                       2022: 72738e6, 2023: 72361e6},
                'da_history': {2019: 11682e6, 2020: 12796e6, 2021: 14460e6,
                               2022: 14460e6, 2023: 13861e6},
                'capex_history': {2019: 15441e6, 2020: 15441e6, 2021: 20622e6,
                                  2022: 23886e6, 2023: 28107e6},
                'revenue_history': {2019: 125843e6, 2020: 143015e6, 2021: 168088e6,
                                    2022: 198270e6, 2023: 211915e6},
                'operating_income_history': {2019: 42959e6, 2020: 52959e6, 2021: 69916e6,
                                             2022: 83383e6, 2023: 88523e6},
                'long_term_debt': 41990e6,
                'equity': 206223e6,
                'shares_outstanding': 7429000000,
            },
        }
        yield mock
