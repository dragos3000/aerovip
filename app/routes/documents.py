"""Student documents: upload / list / download / delete, with expiry tracking.

Students manage their own documents; admins/managers (planners) manage any
student's. Files are stored under instance/uploads/documents/ (gitignored) and
served only to the owner or a planner."""
import os
import uuid
from datetime import date

from flask import (Blueprint, render_template, redirect, url_for, flash, request,
                   current_app, send_from_directory, abort, session)
from flask_login import login_required, current_user

from app import db
from app.models import User, StudentDocument, DOC_TYPES, Setting
from app.forms import DocumentUploadForm, DocumentEditForm
from app.translations import get_translation

bp = Blueprint('documents', __name__, url_prefix='/documents')

ALLOWED_EXT = {'pdf', 'jpg', 'jpeg', 'png'}


def _docs_dir():
    path = os.path.join(current_app.instance_path, 'uploads', 'documents')
    os.makedirs(path, exist_ok=True)
    return path


def _can_access(doc):
    return doc.student_id == current_user.id or current_user.is_planner


def _ext(filename):
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''


def _t(key):
    return get_translation(key, session.get('lang', 'ro'))


@bp.route('/')
@login_required
def index():
    if not (current_user.role == 'student' or current_user.is_planner):
        return redirect(url_for('main.dashboard'))

    form = DocumentUploadForm()
    form.doc_type.choices = [(k, _t('doc.type_' + k)) for k in DOC_TYPES]
    try:
        warn_days = int(Setting.get('doc_expiry_warn_days', '30') or 30)
    except ValueError:
        warn_days = 30

    form.student_id.choices = []
    if current_user.is_planner:
        students = User.query.filter_by(role='student').order_by(User.first_name, User.last_name).all()
        form.student_id.choices = [(s.id, s.full_name) for s in students]
        docs = StudentDocument.query.order_by(
            StudentDocument.student_id, StudentDocument.doc_type,
            StudentDocument.expiry_date.desc()).all()
        # group by student
        by_student = {}
        for d in docs:
            by_student.setdefault(d.student_id, {'student': d.student, 'docs': []})['docs'].append(d)
        groups = sorted(by_student.values(), key=lambda g: g['student'].full_name if g['student'] else '')
        return render_template('documents/list.html', form=form, groups=groups,
                               is_planner=True, doc_types=DOC_TYPES, today=date.today(), warn_days=warn_days)

    docs = StudentDocument.query.filter_by(student_id=current_user.id).order_by(
        StudentDocument.doc_type, StudentDocument.expiry_date.desc()).all()
    return render_template('documents/list.html', form=form, my_docs=docs,
                           is_planner=False, doc_types=DOC_TYPES, today=date.today(), warn_days=warn_days)


@bp.route('/upload', methods=['POST'])
@login_required
def upload():
    if not (current_user.role == 'student' or current_user.is_planner):
        return redirect(url_for('main.dashboard'))

    form = DocumentUploadForm()
    form.doc_type.choices = [(k, _t('doc.type_' + k)) for k in DOC_TYPES]
    form.student_id.choices = ([(s.id, s.full_name) for s in User.query.filter_by(role='student').all()]
                               if current_user.is_planner else [])

    if not form.validate_on_submit():
        flash(_t('doc.upload_failed'), 'danger')
        return redirect(url_for('documents.index'))

    # Who is this for?
    if current_user.is_planner and form.student_id.data:
        target_id = form.student_id.data
        if not User.query.filter_by(id=target_id, role='student').first():
            flash(_t('doc.upload_failed'), 'danger')
            return redirect(url_for('documents.index'))
    else:
        target_id = current_user.id

    f = form.file.data
    ext = _ext(f.filename)
    if ext not in ALLOWED_EXT:
        flash(_t('doc.bad_type'), 'danger')
        return redirect(url_for('documents.index'))

    stored = f'{uuid.uuid4().hex}.{ext}'
    f.save(os.path.join(_docs_dir(), stored))

    doc = StudentDocument(
        student_id=target_id,
        doc_type=form.doc_type.data if form.doc_type.data in DOC_TYPES else 'licence',
        serial=(form.serial.data or '').strip() or None,
        stored_name=stored,
        original_name=f.filename[:256],
        expiry_date=form.expiry_date.data,
        uploaded_by_id=current_user.id,
    )
    db.session.add(doc)
    db.session.commit()
    flash(_t('doc.uploaded'), 'success')
    return redirect(url_for('documents.index'))


@bp.route('/<int:doc_id>/edit', methods=['POST'])
@login_required
def edit(doc_id):
    doc = db.session.get(StudentDocument, doc_id)
    if not doc or not _can_access(doc):
        abort(404)
    form = DocumentEditForm()
    form.doc_type.choices = [(k, _t('doc.type_' + k)) for k in DOC_TYPES]
    if not form.validate_on_submit():
        flash(_t('doc.upload_failed'), 'danger')
        return redirect(url_for('documents.index'))

    doc.doc_type = form.doc_type.data if form.doc_type.data in DOC_TYPES else doc.doc_type
    doc.serial = (form.serial.data or '').strip() or None
    doc.expiry_date = form.expiry_date.data
    # Optional file replacement.
    if form.file.data:
        f = form.file.data
        ext = _ext(f.filename)
        if ext not in ALLOWED_EXT:
            flash(_t('doc.bad_type'), 'danger')
            return redirect(url_for('documents.index'))
        old = doc.stored_name
        stored = f'{uuid.uuid4().hex}.{ext}'
        f.save(os.path.join(_docs_dir(), stored))
        doc.stored_name = stored
        doc.original_name = f.filename[:256]
        try:
            os.remove(os.path.join(_docs_dir(), old))
        except OSError:
            pass
    db.session.commit()
    flash(_t('doc.saved'), 'success')
    return redirect(url_for('documents.index'))


@bp.route('/<int:doc_id>/view')
@login_required
def view(doc_id):
    """Serve the file inline (for in-modal preview)."""
    doc = db.session.get(StudentDocument, doc_id)
    if not doc or not _can_access(doc):
        abort(404)
    return send_from_directory(_docs_dir(), doc.stored_name,
                               as_attachment=False, download_name=doc.original_name)


@bp.route('/<int:doc_id>/download')
@login_required
def download(doc_id):
    doc = db.session.get(StudentDocument, doc_id)
    if not doc or not _can_access(doc):
        abort(404)
    return send_from_directory(_docs_dir(), doc.stored_name,
                               as_attachment=True, download_name=doc.original_name)


@bp.route('/<int:doc_id>/delete', methods=['POST'])
@login_required
def delete(doc_id):
    doc = db.session.get(StudentDocument, doc_id)
    if not doc or not _can_access(doc):
        abort(404)
    try:
        os.remove(os.path.join(_docs_dir(), doc.stored_name))
    except OSError:
        pass
    db.session.delete(doc)
    db.session.commit()
    flash(_t('doc.deleted'), 'info')
    return redirect(url_for('documents.index'))
