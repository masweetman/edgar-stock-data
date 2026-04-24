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
    stock_data = db.relationship('Company', back_populates='user', cascade='all, delete-orphan',
                                 order_by='Company.fetched_at.desc()')

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
    _years = db.Column('years', db.Text, nullable=False, default='[]')
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', back_populates='config')

    @property
    def tickers(self) -> list[str]:
        return json.loads(self._tickers)

    @tickers.setter
    def tickers(self, value: list[str]) -> None:
        self._tickers = json.dumps(value)

    @property
    def years(self) -> list[str]:
        return json.loads(self._years)

    @years.setter
    def years(self, value: list[str]) -> None:
        self._years = json.dumps(value)

    def __repr__(self) -> str:
        return f'<UserConfig user_id={self.user_id}>'


class Company(db.Model):
    __tablename__ = 'companies'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    ticker = db.Column(db.String(20), nullable=False)
    cik = db.Column(db.String(20), nullable=True)
    eps_avg = db.Column(db.Float, nullable=True)
    bvps = db.Column(db.Float, nullable=True)
    div = db.Column(db.Float, nullable=True)
    div_date = db.Column(db.String(20), nullable=True)
    fetched_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = db.relationship('User', back_populates='stock_data')

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'ticker': self.ticker,
            'cik': self.cik,
            'eps_avg': self.eps_avg,
            'bvps': self.bvps,
            'div': self.div,
            'div_date': self.div_date,
            'fetched_at': self.fetched_at.isoformat() if self.fetched_at else None,
        }

    def __repr__(self) -> str:
        return f'<StockDataEntry {self.ticker} user_id={self.user_id}>'
