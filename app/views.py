import base64
import io
import json
import logging
import os
from datetime import datetime, timezone

import certifi
import pyotp
import qrcode
import qrcode.image.svg
from flask import (
    Blueprint,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from app import db, limiter
from app.buffett_calculator import run_buffett_analysis
from app.edgar_service import fetch_data
from app.forms import (
    ConfigForm,
    LoginForm,
    ProfileForm,
    RegisterForm,
    TwoFactorConfirmForm,
    TwoFactorVerifyForm,
)
import yfinance as yf

from app.models import Company, User, UserConfig

# Override any corporate CA bundle path with certifi's verified bundle so that
# yfinance's curl_cffi backend can resolve SSL certificates correctly.
os.environ.setdefault('CURL_CA_BUNDLE', certifi.where())
os.environ['CURL_CA_BUNDLE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()


def _yf_price(ticker: str) -> float | None:
    try:
        return yf.Ticker(ticker).fast_info['last_price']
    except Exception:
        return None

main = Blueprint('main', __name__)
audit_logger = logging.getLogger('audit')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _audit(event: str, user_id=None, extra: dict | None = None) -> None:
    record = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'event': event,
        'user_id': user_id,
        'ip': request.remote_addr,
        **(extra or {}),
    }
    audit_logger.info(json.dumps(record))


def _tickers_from_text(text: str) -> list[str]:
    import re
    valid = re.compile(r'^[A-Z0-9.\-]{1,10}$')
    return [t for t in (t.strip().upper() for t in text.splitlines() if t.strip()) if valid.match(t)]



# ---------------------------------------------------------------------------
# HTML Routes
# ---------------------------------------------------------------------------

@main.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('main.login'))


@main.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            _audit('login_failed', extra={'username': form.username.data})
            form.password.errors.append('Invalid username or password.')
            return render_template('login.html', form=form), 401

        if user.two_factor_enabled:
            # Store pending user ID in session for 2FA step
            session['pending_2fa_user_id'] = user.id
            session['pending_2fa_remember'] = form.remember_me.data
            return redirect(url_for('main.login_2fa'))

        login_user(user, remember=form.remember_me.data)
        _audit('login_success', user_id=user.id)
        return redirect(url_for('main.dashboard'))

    return render_template('login.html', form=form)


@main.route('/login/2fa', methods=['GET', 'POST'])
@limiter.limit('5 per minute')
def login_2fa():
    user_id = session.get('pending_2fa_user_id')
    if not user_id:
        return redirect(url_for('main.login'))

    user = db.session.get(User, user_id)
    if user is None:
        return redirect(url_for('main.login'))

    form = TwoFactorVerifyForm()
    if form.validate_on_submit():
        totp = pyotp.TOTP(user.two_factor_secret)
        if not totp.verify(form.code.data, valid_window=1):
            _audit('2fa_verify_failed', user_id=user.id)
            form.code.errors.append('Invalid or expired code.')
            return render_template('login_2fa.html', form=form), 401

        remember = session.pop('pending_2fa_remember', False)
        session.pop('pending_2fa_user_id', None)
        login_user(user, remember=remember)
        _audit('login_success_2fa', user_id=user.id)
        return redirect(url_for('main.dashboard'))

    return render_template('login_2fa.html', form=form)


@main.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            form.username.errors.append('Username already taken.')
            return render_template('register.html', form=form)
        if User.query.filter_by(email=form.email.data).first():
            form.email.errors.append('Email already registered.')
            return render_template('register.html', form=form)

        is_first_user = User.query.count() == 0
        user = User(username=form.username.data, email=form.email.data, is_admin=is_first_user)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        _audit('register', user_id=user.id, extra={'is_admin': is_first_user})
        login_user(user)
        return redirect(url_for('main.config'))

    return render_template('register.html', form=form)


@main.route('/logout')
@login_required
def logout():
    _audit('logout', user_id=current_user.id)
    logout_user()
    return redirect(url_for('main.login'))


@main.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    two_factor_confirm_form = TwoFactorConfirmForm()

    if form.validate_on_submit():
        # Email update
        if form.email.data != current_user.email:
            if User.query.filter(User.email == form.email.data, User.id != current_user.id).first():
                form.email.errors.append('Email already in use.')
                return render_template('profile.html', form=form,
                                       two_factor_confirm_form=two_factor_confirm_form)
            current_user.email = form.email.data

        # Password change
        if form.new_password.data:
            if not form.current_password.data or not current_user.check_password(form.current_password.data):
                form.current_password.errors.append('Current password is incorrect.')
                return render_template('profile.html', form=form,
                                       two_factor_confirm_form=two_factor_confirm_form)
            current_user.set_password(form.new_password.data)
            _audit('password_changed', user_id=current_user.id)

        db.session.commit()
        if form.new_password.data:
            # Regenerate session to invalidate any old sessions (NIST SP 800-63B §7)
            user_ref = current_user._get_current_object()
            logout_user()
            login_user(user_ref)
        return redirect(url_for('main.profile'))

    return render_template('profile.html', form=form,
                           two_factor_confirm_form=two_factor_confirm_form)


@main.route('/config', methods=['GET', 'POST'])
@login_required
def config():
    cfg = current_user.get_or_create_config()
    db.session.flush()

    form = ConfigForm()
    if request.method == 'GET':
        form.sec_email.data = cfg.sec_email
        form.tickers.data = '\n'.join(cfg.tickers)
        form.discount_rate.data = cfg.discount_rate

    if form.validate_on_submit():
        cfg.sec_email = form.sec_email.data
        cfg.tickers = _tickers_from_text(form.tickers.data)
        cfg.discount_rate = float(form.discount_rate.data)
        db.session.commit()
        return redirect(url_for('main.dashboard'))

    return render_template('config.html', form=form)


@main.route('/dashboard')
@login_required
def dashboard():
    cfg = current_user.config
    tickers = cfg.tickers if cfg else []

    entries: list[Company] = []
    if tickers:
        entries = (
            Company.query
            .filter(Company.ticker.in_(tickers))
            .order_by(Company.ticker)
            .all()
        )

    prices: dict[str, float | None] = {}
    for entry in entries:
        prices[entry.ticker] = _yf_price(entry.ticker)

    return render_template('dashboard.html', entries=entries, prices=prices, config=cfg)


@main.route('/company/<ticker>')
@login_required
def company(ticker: str):
    from app.buffett_calculator import calculate_margin_of_safety, mos_signal as _mos_signal
    from flask import abort

    ticker_upper = ticker.upper()
    cfg = current_user.config
    if cfg is None or ticker_upper not in cfg.tickers:
        abort(403)

    entries = (
        Company.query
        .filter_by(ticker=ticker_upper)
        .order_by(Company.fetched_at.desc())
        .all()
    )
    if not entries:
        abort(404)

    price: float | None = _yf_price(ticker)

    # Compute MOS dynamically from live price and stored intrinsic value
    latest = entries[0]
    mos: float | None = calculate_margin_of_safety(price, latest.intrinsic_value)
    signal: str = _mos_signal(mos)
    discount_rate = current_user.config.discount_rate if current_user.config else 0.09

    return render_template(
        'company.html',
        ticker=ticker.upper(),
        entries=entries,
        price=price,
        mos=mos,
        mos_signal=signal,
        discount_rate=discount_rate,
    )


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@main.route('/api/fetch', methods=['POST'])
@login_required
@limiter.limit('10 per hour')
def api_fetch():
    cfg = current_user.config
    if cfg is None or not cfg.sec_email or not cfg.tickers:
        return jsonify({'success': False, 'error': 'Please configure your tickers and SEC email first.'}), 400

    # Capture log output from the edgar service during the fetch so the UI can display it.
    class _ListHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.lines: list[str] = []

        def emit(self, record: logging.LogRecord) -> None:
            self.lines.append(self.format(record))

    log_handler = _ListHandler()
    log_handler.setFormatter(logging.Formatter('%(levelname)s  %(message)s'))
    log_handler.setLevel(logging.DEBUG)

    capture_loggers = [
        logging.getLogger('app.edgar_service'),
        logging.getLogger('edgar'),
    ]
    original_levels: dict[logging.Logger, int] = {}
    for lg in capture_loggers:
        original_levels[lg] = lg.level
        lg.setLevel(logging.DEBUG)
        lg.addHandler(log_handler)

    try:
        verify_ssl = current_app.config.get('EDGAR_VERIFY_SSL', True)
        results = fetch_data(cfg.sec_email, cfg.tickers, verify_ssl=verify_ssl)
    except Exception as exc:
        logging.getLogger('app').error('Edgar fetch error for user %s: %s', current_user.id, exc)
        return jsonify({'success': False, 'error': 'Failed to fetch data from SEC EDGAR.', 'logs': log_handler.lines}), 502
    finally:
        for lg in capture_loggers:
            lg.removeHandler(log_handler)
            lg.setLevel(original_levels[lg])

    discount_rate = float(cfg.discount_rate) if cfg.discount_rate else 0.09

    now = datetime.now(timezone.utc)
    saved = []
    for ticker, data in results.items():
        buffett = run_buffett_analysis(data, discount_rate)
        entry = Company.query.filter_by(ticker=ticker).first()
        if entry is None:
            entry = Company(ticker=ticker)
            db.session.add(entry)
        entry.cik = data.get('cik')
        entry.eps_avg = data.get('eps_avg')
        entry.bvps = data.get('bvps')
        entry.div = data.get('div')
        entry.div_date = data.get('div_date')
        entry.owner_earnings = buffett.get('owner_earnings')
        entry.intrinsic_value = buffett.get('intrinsic_value')
        entry.quality_score = buffett.get('quality_score')
        entry.growth_rate_used = buffett.get('growth_rate_used')
        entry.fetched_at = now
        saved.append(entry)

    db.session.commit()
    _audit('data_fetched', user_id=current_user.id, extra={'tickers': cfg.tickers})

    return jsonify({
        'success': True,
        'data': [e.to_dict() for e in saved],
        'logs': log_handler.lines,
    })


@main.route('/api/2fa/setup', methods=['GET'])
@login_required
def api_2fa_setup():
    if current_user.two_factor_enabled:
        return jsonify({'success': False, 'error': '2FA is already enabled.'}), 400

    secret = pyotp.random_base32()
    # Store temporarily in session (not in DB until confirmed)
    from flask import session
    session['pending_2fa_secret'] = secret

    uri = pyotp.TOTP(secret).provisioning_uri(
        name=current_user.username,
        issuer_name='EDGAR Stock Data',
    )

    # Generate QR code as base64 PNG
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return jsonify({
        'success': True,
        'secret': secret,
        'qr_image': f'data:image/png;base64,{qr_b64}',
    })


@main.route('/api/2fa/enable', methods=['POST'])
@login_required
@limiter.limit('5 per minute')
def api_2fa_enable():
    data = request.get_json(silent=True) or {}
    password = data.get('password', '')
    code = str(data.get('code', ''))
    secret = session.get('pending_2fa_secret')

    if not current_user.check_password(password):
        _audit('2fa_enable_failed', user_id=current_user.id, extra={'reason': 'bad_password'})
        return jsonify({'success': False, 'error': 'Current password is incorrect.'}), 400

    if not secret:
        return jsonify({'success': False, 'error': 'No pending 2FA setup. Request setup first.'}), 400

    totp = pyotp.TOTP(secret)
    if not totp.verify(code, valid_window=1):
        _audit('2fa_enable_failed', user_id=current_user.id, extra={'reason': 'bad_code'})
        return jsonify({'success': False, 'error': 'Invalid or expired code.'}), 400

    current_user.two_factor_secret = secret
    current_user.two_factor_enabled = True
    db.session.commit()
    session.pop('pending_2fa_secret', None)
    _audit('2fa_enabled', user_id=current_user.id)

    return jsonify({'success': True})


@main.route('/api/2fa/disable', methods=['POST'])
@login_required
@limiter.limit('5 per minute')
def api_2fa_disable():
    data = request.get_json(silent=True) or {}
    password = data.get('password', '')
    code = str(data.get('code', ''))

    if not current_user.two_factor_enabled:
        return jsonify({'success': False, 'error': '2FA is not enabled.'}), 400

    if not current_user.check_password(password):
        _audit('2fa_disable_failed', user_id=current_user.id, extra={'reason': 'bad_password'})
        return jsonify({'success': False, 'error': 'Current password is incorrect.'}), 400

    totp = pyotp.TOTP(current_user.two_factor_secret)
    if not totp.verify(code, valid_window=1):
        _audit('2fa_disable_failed', user_id=current_user.id, extra={'reason': 'bad_code'})
        return jsonify({'success': False, 'error': 'Invalid or expired code.'}), 400

    current_user.two_factor_enabled = False
    current_user.two_factor_secret = None
    db.session.commit()
    _audit('2fa_disabled', user_id=current_user.id)

    return jsonify({'success': True})
