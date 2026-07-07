from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired


class LoginForm(FlaskForm):
    username: StringField = StringField(
        "Username",
        id="username_login",
        validators=[DataRequired()],
    )
    password: PasswordField = PasswordField(
        "Password",
        id="pwd_login",
        validators=[DataRequired()],
    )
