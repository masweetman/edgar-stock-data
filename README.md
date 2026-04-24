# edgar-stock-data

A multi-user Flask web app that pulls fundamental stock data (EPS, BVPS, dividends) from the [SEC EDGAR API](https://www.sec.gov/edgar/sec-api-documentation) via [edgartools](https://github.com/dgunning/edgartools) and stores results in a SQLite database.

Each user manages their own watchlist of tickers and year range, and can fetch the latest data on demand from a dashboard.

## Features

- User accounts with open registration
- Per-user configuration: SEC identity email, ticker watchlist, year range for EPS averaging
- On-demand data fetch from SEC EDGAR (EPS avg, BVPS, dividends)
- Results stored in SQLite and displayed in a dashboard table
- Optional TOTP two-factor authentication (authenticator app + QR code)
- Admin panel (Flask-Admin) for user management

## Data collected

- **EPS (Avg)** — average annual diluted earnings per share over the configured years
- **BVPS** — book value per share (assets − liabilities) ÷ shares outstanding
- **Dividend** — most recent dividend per share and declaration date

## Getting started

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd edgar-stock-data
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env and set SECRET_KEY to a long random string
```

### 3. Run the app

```bash
flask --app run.py run
```

The app automatically applies database migrations on startup — no separate `flask db upgrade` step required.

Open `http://localhost:5000`, register an account, fill in your configuration, and click **Fetch Latest Data**.

## Database migrations

After pulling model changes:

```bash
flask --app run.py db migrate -m "description"
flask --app run.py db upgrade
```

## Running tests

```bash
pytest -v
```

Tests use an in-memory SQLite database and mock all SEC EDGAR network calls.

## Production deployment

Run with Gunicorn behind a reverse proxy (e.g. nginx):

```bash
gunicorn -w 4 "run:app"
```

Set `FLASK_CONFIG=production` and `SESSION_COOKIE_SECURE=True` in your environment. Serve only over HTTPS.

## Project structure

```
edgar-stock-data/
├── run.py                  ← entry point
├── requirements.txt
├── .env.example
├── app/
│   ├── __init__.py         ← app factory
│   ├── configuration.py    ← Dev / Test / Prod config
│   ├── models.py           ← User, UserConfig, StockDataEntry
│   ├── forms.py            ← WTForms form classes
│   ├── views.py            ← HTML routes + /api/* endpoints
│   ├── admin_views.py      ← Flask-Admin (admin-only)
│   ├── edgar_service.py    ← SEC EDGAR fetch logic (edgartools)
│   ├── static/
│   └── templates/
├── migrations/
└── tests/
```

## SEC EDGAR identity requirement

The SEC requires all API consumers to identify themselves via a `User-Agent` header. Each user must enter their email address in the **Config** page — this is passed to `edgartools` via `set_identity()` before any SEC requests are made. See the [SEC webmaster FAQ](https://www.sec.gov/os/webmaster-faq#developers).
