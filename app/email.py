"""Minimal SMTP email sender. Credentials live in the `Setting` table (configured
in admin Settings), so they're read at send time and can change at runtime. Sends
in a daemon thread so a slow SMTP server never blocks the request."""
import smtplib
import threading
from email.message import EmailMessage

from flask import current_app
from app.models import Setting


def email_configured():
    """True when enough SMTP settings exist to attempt a send."""
    return bool(Setting.get('smtp_host', '') and (Setting.get('smtp_from', '') or Setting.get('smtp_user', '')))


def _truthy(v):
    return str(v) in ('1', 'true', 'True', 'on', 'yes')


def _send(app, to, subject, html, text):
    with app.app_context():
        host = Setting.get('smtp_host', '')
        if not host:
            current_app.logger.warning('Email: SMTP not configured — skipping send to %s', to)
            return
        try:
            port = int(Setting.get('smtp_port', '587') or 587)
        except ValueError:
            port = 587
        user = Setting.get('smtp_user', '')
        pwd = Setting.get('smtp_pass', '')
        sender = Setting.get('smtp_from', '') or user
        use_tls = _truthy(Setting.get('smtp_tls', '1'))

        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = to
        msg.set_content(text or 'Open this email in an HTML-capable client.')
        if html:
            msg.add_alternative(html, subtype='html')

        try:
            if port == 465:
                with smtplib.SMTP_SSL(host, port, timeout=20) as s:
                    if user:
                        s.login(user, pwd)
                    s.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=20) as s:
                    if use_tls:
                        s.starttls()
                    if user:
                        s.login(user, pwd)
                    s.send_message(msg)
            current_app.logger.info('Email sent to %s', to)
        except Exception:
            current_app.logger.exception('Email: send to %s failed', to)


def send_email_async(to, subject, html, text=None):
    """Fire-and-forget send on a background thread."""
    app = current_app._get_current_object()
    threading.Thread(target=_send, args=(app, to, subject, html, text), daemon=True).start()
