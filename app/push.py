"""Web Push sender (VAPID). Keys live in the Setting table; sends run on a daemon
thread so requests aren't blocked. A no-op when VAPID isn't configured."""
import json
import threading
from datetime import date

from flask import current_app
from app import db
from app.models import Setting, PushSubscription


def vapid_configured():
    return bool(Setting.get('vapid_public', '') and Setting.get('vapid_private', ''))


def _deliver(app, user_ids, title, body, url):
    from pywebpush import webpush, WebPushException
    with app.app_context():
        priv = Setting.get('vapid_private', '')
        contact = Setting.get('vapid_contact', '') or 'mailto:admin@aerovip.ro'
        if not priv:
            return
        payload = json.dumps({'title': title, 'body': body, 'url': url or ''})
        subs = PushSubscription.query.filter(PushSubscription.user_id.in_(list(user_ids))).all()
        for sub in subs:
            try:
                webpush(subscription_info=sub.as_info(), data=payload,
                        vapid_private_key=priv, vapid_claims={'sub': contact},
                        ttl=86400)   # hold up to 24h if the device is briefly offline
            except WebPushException as e:
                status = getattr(e.response, 'status_code', None)
                if status in (404, 410):                 # gone — drop the dead subscription
                    db.session.delete(sub)
            except Exception:
                current_app.logger.exception('Push: send failed')
        db.session.commit()


def send_push(user_id, title, body, url=None):
    send_push_many([user_id], title, body, url)


def send_push_many(user_ids, title, body, url=None):
    ids = [i for i in set(user_ids) if i]
    if not ids or not vapid_configured():
        return
    app = current_app._get_current_object()
    threading.Thread(target=_deliver, args=(app, ids, title, body, url), daemon=True).start()


def push_expiring_documents(app):
    """Once per day: notify students (and planners) about documents that are expiring
    soon or expired. Guarded by a Setting so it runs at most once per calendar day."""
    with app.app_context():
        if not vapid_configured():
            return
        today = date.today()
        if Setting.get('doc_push_last_date', '') == today.isoformat():
            return
        from app.models import StudentDocument, User
        try:
            warn = int(Setting.get('doc_expiry_warn_days', '30') or 30)
        except ValueError:
            warn = 30
        current = {}
        for d in StudentDocument.query.order_by(StudentDocument.expiry_date.desc()).all():
            current.setdefault((d.student_id, d.doc_type), d)
        flagged = []
        for d in current.values():
            days = (d.expiry_date - today).days
            if days <= warn:
                flagged.append((d, days))
        Setting.set('doc_push_last_date', today.isoformat(), 'Last day document-expiry push ran')
        if not flagged:
            return
        planner_ids = [u.id for u in User.query.filter(User.role.in_(('admin', 'manager')),
                                                       User.is_active == True).all()]  # noqa: E712
        from app.translations import get_translation as _g
        for d, days in flagged:
            label = _g('doc.type_' + d.doc_type, 'ro')
            sname = d.student.full_name if d.student else ''
            if days < 0:
                body_self = f"{label}: {_g('doc.expired', 'ro')} ({d.expiry_date:%d %b %Y})"
            else:
                body_self = f"{label}: {_g('doc.expiring', 'ro')} {days}{_g('doc.days_short', 'ro')} ({d.expiry_date:%d %b %Y})"
            send_push(d.student_id, _g('push.doc_title', 'ro'), body_self, url='/documents/')
            if planner_ids:
                send_push_many(planner_ids, _g('push.doc_title', 'ro'), f"{sname} — {body_self}", url='/documents/')
