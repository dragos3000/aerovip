"""Web Push subscription endpoints (save/remove a browser's push subscription)."""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from app import db
from app.models import PushSubscription

bp = Blueprint('push', __name__, url_prefix='/push')


@bp.route('/subscribe', methods=['POST'])
@login_required
def subscribe():
    data = request.get_json(silent=True) or {}
    endpoint = data.get('endpoint')
    keys = data.get('keys') or {}
    p256dh, auth = keys.get('p256dh'), keys.get('auth')
    if not (endpoint and p256dh and auth):
        return jsonify({'ok': False, 'error': 'Invalid subscription.'}), 400

    sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if sub:
        sub.user_id = current_user.id
        sub.p256dh = p256dh
        sub.auth = auth
    else:
        db.session.add(PushSubscription(user_id=current_user.id, endpoint=endpoint,
                                        p256dh=p256dh, auth=auth))
    db.session.commit()
    return jsonify({'ok': True})


@bp.route('/unsubscribe', methods=['POST'])
@login_required
def unsubscribe():
    data = request.get_json(silent=True) or {}
    endpoint = data.get('endpoint')
    if endpoint:
        PushSubscription.query.filter_by(endpoint=endpoint).delete()
        db.session.commit()
    return jsonify({'ok': True})
