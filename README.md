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

The application is served by **Gunicorn** on a Unix socket and fronted by **OpenLiteSpeed** as the reverse proxy. A systemd unit file is provided in `deploy/edgar-stock-data.service`.

### Prerequisites

- Python 3.11+
- OpenLiteSpeed installed and running
- A domain name with DNS pointed at the server

### 1. Create the app directory and user

```bash
sudo mkdir -p /srv/edgar-stock-data
sudo chown nobody:nogroup /srv/edgar-stock-data
```

> `nobody` is the default user/group for OpenLiteSpeed on Debian/Ubuntu. Adjust if your distro differs (e.g. `nobody` on CentOS/RHEL, or a custom OLS service account).

### 2. Clone the repository and set up the virtual environment

```bash
sudo -u nobody git clone <repo-url> /srv/edgar-stock-data
cd /srv/edgar-stock-data
sudo -u nobody python3 -m venv .venv
sudo -u nobody .venv/bin/pip install -r requirements.txt
```

### 3. Configure the production environment

```bash
sudo -u nobody cp .env.example .env
sudo -u nobody nano .env
```

Required values in `.env`:

```ini
SECRET_KEY=<long-random-string>     # generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
FLASK_CONFIG=production
SESSION_COOKIE_SECURE=True
```

### 4. Create the log directory

```bash
sudo mkdir -p /var/log/edgar-stock-data
sudo chown nobody:nogroup /var/log/edgar-stock-data
```

### 5. Install and start the systemd service

```bash
sudo cp /srv/edgar-stock-data/deploy/edgar-stock-data.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now edgar-stock-data
```

Verify it is running:

```bash
sudo systemctl status edgar-stock-data
```

The Unix socket is created at `/run/edgar-stock-data/gunicorn.sock`.

To reload workers after a code update without dropping connections:

```bash
sudo systemctl reload edgar-stock-data
```

### 6. Configure OpenLiteSpeed

All steps are performed in the **OpenLiteSpeed Web Admin** console (default: `https://<server-ip>:7080`).

#### 6a. Create an External App

1. Go to **Virtual Hosts → \<your vhost\> → External Apps** → click **+**
2. Set the fields:

   | Field | Value |
   |---|---|
   | Type | Web Server |
   | Name | `edgar-gunicorn` |
   | Address | `uds://run/edgar-stock-data/gunicorn.sock` |
   | Max Connections | `10` |
   | Initial Request Timeout | `120` |
   | Retry Timeout | `0` |

3. Click **Save**.

#### 6b. Add a Proxy Context

1. Go to **Virtual Hosts → \<your vhost\> → Context** → click **+**
2. Set the fields:

   | Field | Value |
   |---|---|
   | Type | Proxy |
   | URI | `/` |
   | Web Server | `edgar-gunicorn` |

3. Click **Save**.

#### 6c. Configure the Virtual Host document root

1. Go to **Virtual Hosts → \<your vhost\> → General**
2. Set **Document Root** to `/srv/edgar-stock-data/app/static`

   > This is only used if you later serve static files directly from OLS. With a pure proxy context the Flask app handles static files.

#### 6d. Enable HTTPS

1. Go to **Listeners** and ensure you have an HTTPS listener on port 443 with your SSL certificate configured.
2. Add your virtual host to that listener.
3. To redirect HTTP → HTTPS, go to **Virtual Hosts → \<your vhost\> → Rewrite** and enable rewrite rules:

   ```
   RewriteEngine on
   RewriteCond %{SERVER_PORT} !^443$
   RewriteRule ^(.*)$ https://%{HTTP_HOST}%{REQUEST_URI} [R=301,L]
   ```

4. Click **Save** and then **Graceful Restart** (the green restart button in the top-right corner).

### Updating the application

```bash
cd /srv/edgar-stock-data
sudo -u nobody git pull
sudo -u nobody .venv/bin/pip install -r requirements.txt
sudo systemctl reload edgar-stock-data
```

Database migrations are applied automatically on startup when `FLASK_CONFIG=production`. A `systemctl reload` sends `SIGHUP` to Gunicorn, which spawns fresh workers that pick up code and migration changes with no downtime.

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
