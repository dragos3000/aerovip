from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, session
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app import db
from app.models import User
from app.forms import LoginForm, RegistrationForm, ForgotPasswordForm, ResetPasswordForm
from app.translations import get_translation

bp = Blueprint('auth', __name__, url_prefix='/auth')


def _reset_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='pwd-reset')


RESET_MAX_AGE = 3600   # reset links valid for 1 hour


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash('Your account has been deactivated. Contact an administrator.', 'danger')
                return render_template('auth/login.html', form=form)
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.dashboard'))
        flash('Invalid email or password.', 'danger')

    return render_template('auth/login.html', form=form)


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = RegistrationForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data.lower()).first():
            flash('Email already registered.', 'danger')
            return render_template('auth/register.html', form=form)

        user = User(
            email=form.email.data.lower(),
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            phone=form.phone.data,
            role='student',
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! You can now log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', form=form)


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@bp.route('/forgot', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    lang = session.get('lang', 'ro')
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        from app.email import send_email_async
        email = form.email.data.lower().strip()
        user = User.query.filter_by(email=email).first()
        if user and user.is_active:
            token = _reset_serializer().dumps(user.id)
            link = url_for('auth.reset_password', token=token, _external=True)
            subject = get_translation('email.reset_subject', lang)
            html = render_template('email/reset_password.html', user=user, link=link, lang=lang)
            send_email_async(user.email, subject, html,
                             text=get_translation('email.reset_body', lang) + '\n\n' + link)
        # Always the same response — don't reveal whether the email exists.
        flash(get_translation('auth.reset_sent', lang), 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot.html', form=form)


@bp.route('/reset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    lang = session.get('lang', 'ro')
    try:
        user_id = _reset_serializer().loads(token, max_age=RESET_MAX_AGE)
    except SignatureExpired:
        flash(get_translation('auth.reset_expired', lang), 'danger')
        return redirect(url_for('auth.forgot_password'))
    except BadSignature:
        flash(get_translation('auth.reset_invalid', lang), 'danger')
        return redirect(url_for('auth.forgot_password'))

    user = db.session.get(User, user_id)
    if not user or not user.is_active:
        flash(get_translation('auth.reset_invalid', lang), 'danger')
        return redirect(url_for('auth.forgot_password'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash(get_translation('auth.reset_done', lang), 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/reset.html', form=form)
