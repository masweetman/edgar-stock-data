from flask_wtf import FlaskForm
from wtforms import BooleanField, DecimalField, EmailField, PasswordField, StringField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, Optional, Regexp


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(max=64)])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember me')


class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    email = EmailField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField(
        'Password',
        validators=[
            DataRequired(),
            Length(min=8, max=64, message='Password must be between 8 and 64 characters.'),
        ],
    )
    password_confirm = PasswordField(
        'Confirm Password',
        validators=[DataRequired(), EqualTo('password', message='Passwords must match.')],
    )


class ProfileForm(FlaskForm):
    email = EmailField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    current_password = PasswordField('Current Password', validators=[Optional()])
    new_password = PasswordField(
        'New Password',
        validators=[
            Optional(),
            Length(min=8, max=64, message='Password must be between 8 and 64 characters.'),
        ],
    )
    new_password_confirm = PasswordField(
        'Confirm New Password',
        validators=[Optional(), EqualTo('new_password', message='Passwords must match.')],
    )


class ConfigForm(FlaskForm):
    sec_email = EmailField(
        'SEC Identity Email',
        validators=[DataRequired(), Email(), Length(max=120)],
        description='Used as the User-Agent for SEC EDGAR requests (required by SEC).',
    )
    tickers = TextAreaField(
        'Tickers',
        validators=[DataRequired()],
        description='One ticker per line (e.g. AAPL).',
    )
    discount_rate = DecimalField(
        'Discount Rate',
        validators=[
            DataRequired(),
            NumberRange(min=0.01, max=0.30, message='Discount rate must be between 1% and 30%.'),
        ],
        places=4,
        default=0.09,
        description='Annual discount rate used for the intrinsic value DCF model (e.g. 0.09 for 9%).',
    )


class TwoFactorVerifyForm(FlaskForm):
    code = StringField('Authenticator Code', validators=[
        DataRequired(), Length(min=6, max=6), Regexp(r'^\d{6}$', message='Code must be 6 digits.'),
    ])


class TwoFactorConfirmForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    code = StringField('Authenticator Code', validators=[
        DataRequired(), Length(min=6, max=6), Regexp(r'^\d{6}$', message='Code must be 6 digits.'),
    ])
