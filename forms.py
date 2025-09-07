from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, Email, EqualTo


class LoginForm(FlaskForm):
    """
    This form handles user login.
    A permanent fix for the UndefinedError is to ensure all
    fields used in the template (e.g., 'username') are defined here.
    """
    username = StringField(
        'Username',
        validators=[
            DataRequired(),  # Ensures the field is not empty
            Length(min=4, max=25)  # Sets a minimum and maximum length
        ]
    )
    password = PasswordField(
        'Password',
        validators=[DataRequired()]
    )
    submit = SubmitField('Log In')


class RegistrationForm(FlaskForm):
    """
    This form handles new user registration.
    """
    username = StringField(
        'Username',
        validators=[
            DataRequired(),
            Length(min=4, max=25)
        ]
    )
    email = StringField(
        'Email',
        validators=[
            DataRequired(),
            Email()
        ]
    )
    password = PasswordField(
        'Password',
        validators=[DataRequired()]
    )
    confirm_password = PasswordField(
        'Confirm Password',
        validators=[
            DataRequired(),
            EqualTo('password', message='Passwords must match.')
        ]
    )
    submit = SubmitField('Register')
