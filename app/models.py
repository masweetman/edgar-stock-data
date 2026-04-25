import json
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    two_factor_enabled = db.Column(db.Boolean, default=False, nullable=False)
    two_factor_secret = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    config = db.relationship('UserConfig', uselist=False, back_populates='user', cascade='all, delete-orphan')

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def get_or_create_config(self) -> 'UserConfig':
        if self.config is None:
            cfg = UserConfig(user=self)
            db.session.add(cfg)
        return self.config

    def __repr__(self) -> str:
        return f'<User {self.username}>'


@login_manager.user_loader
def load_user(user_id: str):
    try:
        return db.session.get(User, int(user_id))
    except Exception:
        return None


class UserConfig(db.Model):
    __tablename__ = 'user_configs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    sec_email = db.Column(db.String(120), nullable=False, default='')
    _tickers = db.Column('tickers', db.Text, nullable=False, default='[]')
    discount_rate = db.Column(db.Float, nullable=False, default=0.09)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', back_populates='config')

    @property
    def tickers(self) -> list[str]:
        return json.loads(self._tickers)

    @tickers.setter
    def tickers(self, value: list[str]) -> None:
        self._tickers = json.dumps(value)

    def __repr__(self) -> str:
        return f'<UserConfig user_id={self.user_id}>'


class Company(db.Model):
    __tablename__ = 'companies'
    __table_args__ = (db.UniqueConstraint('ticker', name='uq_company_ticker'),)

    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(20), nullable=False, unique=True, index=True)
    cik = db.Column(db.String(20), nullable=True)
    eps_avg = db.Column(db.Float, nullable=True)
    bvps = db.Column(db.Float, nullable=True)
    div = db.Column(db.Float, nullable=True)
    div_date = db.Column(db.String(20), nullable=True)
    owner_earnings = db.Column(db.Float, nullable=True)
    normalized_owner_earnings = db.Column(db.Float, nullable=True)
    oe_is_noisy = db.Column(db.Boolean, nullable=True)
    intrinsic_value = db.Column(db.Float, nullable=True)
    quality_score = db.Column(db.Integer, nullable=True)
    growth_rate_used = db.Column(db.Float, nullable=True)
    net_debt = db.Column(db.Float, nullable=True)
    debt_unreliable = db.Column(db.Boolean, nullable=True)
    iv_sensitivity_low = db.Column(db.Float, nullable=True)   # IV at discount_rate + 2%
    iv_sensitivity_high = db.Column(db.Float, nullable=True)  # IV at discount_rate - 2%
    capital_intensity = db.Column(db.Float, nullable=True)
    earnings_consistency_cv = db.Column(db.Float, nullable=True)
    earnings_consistency_label = db.Column(db.String(10), nullable=True)
    predictability_rating = db.Column(db.String(10), nullable=True)
    fetched_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    annual_eps_records = db.relationship(
        'AnnualEPS', back_populates='company', cascade='all, delete-orphan',
        order_by='AnnualEPS.year',
    )
    dividend_records = db.relationship(
        'Dividend', back_populates='company', cascade='all, delete-orphan',
        order_by='Dividend.dividend_date.desc()',
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'ticker': self.ticker,
            'cik': self.cik,
            'eps_avg': self.eps_avg,
            'bvps': self.bvps,
            'div': self.div,
            'div_date': self.div_date,
            'owner_earnings': self.owner_earnings,
            'normalized_owner_earnings': self.normalized_owner_earnings,
            'oe_is_noisy': self.oe_is_noisy,
            'intrinsic_value': self.intrinsic_value,
            'quality_score': self.quality_score,
            'growth_rate_used': self.growth_rate_used,
            'net_debt': self.net_debt,
            'debt_unreliable': self.debt_unreliable,
            'iv_sensitivity_low': self.iv_sensitivity_low,
            'iv_sensitivity_high': self.iv_sensitivity_high,
            'capital_intensity': self.capital_intensity,
            'earnings_consistency_cv': self.earnings_consistency_cv,
            'earnings_consistency_label': self.earnings_consistency_label,
            'predictability_rating': self.predictability_rating,
            'fetched_at': self.fetched_at.isoformat() if self.fetched_at else None,
        }

    def __repr__(self) -> str:
        return f'<Company {self.ticker}>'


class AnnualEPS(db.Model):
    __tablename__ = 'annual_eps'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'year', name='uq_annual_eps_company_year'),
    )

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    value = db.Column(db.Float, nullable=False)
    avg_3yr = db.Column(db.Float, nullable=True)
    avg_6yr = db.Column(db.Float, nullable=True)

    company = db.relationship('Company', back_populates='annual_eps_records')

    def __repr__(self) -> str:
        return f'<AnnualEPS company_id={self.company_id} year={self.year} value={self.value}>'


class Dividend(db.Model):
    __tablename__ = 'dividends'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'dividend_date', name='uq_dividend_company_date'),
    )

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    dividend_date = db.Column(db.String(20), nullable=False)
    dividend_period = db.Column(db.String(20), nullable=False)
    value = db.Column(db.Float, nullable=False)

    company = db.relationship('Company', back_populates='dividend_records')

    def __repr__(self) -> str:
        return f'<Dividend company_id={self.company_id} date={self.dividend_date} value={self.value}>'
