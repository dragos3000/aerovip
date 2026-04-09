from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import Aircraft
from app.forms import AircraftForm

bp = Blueprint('aircraft', __name__, url_prefix='/aircraft')


@bp.route('/')
@login_required
def list_aircraft():
    aircraft_list = Aircraft.query.order_by(Aircraft.registration).all()
    return render_template('aircraft/list.html', aircraft=aircraft_list)


@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if current_user.role not in ('admin', 'instructor'):
        flash('Permission denied.', 'danger')
        return redirect(url_for('aircraft.list_aircraft'))

    form = AircraftForm()
    if form.validate_on_submit():
        if Aircraft.query.filter_by(registration=form.registration.data.upper()).first():
            flash('Aircraft with this registration already exists.', 'danger')
            return render_template('aircraft/form.html', form=form, title='Add Aircraft')

        ac = Aircraft(
            registration=form.registration.data.upper(),
            aircraft_type=form.aircraft_type.data,
            model=form.model.data,
            seats=form.seats.data,
            hourly_rate=form.hourly_rate.data,
            is_available=form.is_available.data,
            image_url=form.image_url.data,
            notes=form.notes.data,
        )
        db.session.add(ac)
        db.session.commit()
        flash('Aircraft added successfully.', 'success')
        return redirect(url_for('aircraft.list_aircraft'))

    return render_template('aircraft/form.html', form=form, title='Add Aircraft')


@bp.route('/<int:aircraft_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(aircraft_id):
    if current_user.role not in ('admin', 'instructor'):
        flash('Permission denied.', 'danger')
        return redirect(url_for('aircraft.list_aircraft'))

    ac = db.session.get(Aircraft, aircraft_id)
    if not ac:
        flash('Aircraft not found.', 'danger')
        return redirect(url_for('aircraft.list_aircraft'))

    form = AircraftForm(obj=ac)
    if form.validate_on_submit():
        existing = Aircraft.query.filter_by(registration=form.registration.data.upper()).first()
        if existing and existing.id != ac.id:
            flash('Another aircraft with this registration already exists.', 'danger')
            return render_template('aircraft/form.html', form=form, title='Edit Aircraft')

        ac.registration = form.registration.data.upper()
        ac.aircraft_type = form.aircraft_type.data
        ac.model = form.model.data
        ac.seats = form.seats.data
        ac.hourly_rate = form.hourly_rate.data
        ac.is_available = form.is_available.data
        ac.image_url = form.image_url.data
        ac.notes = form.notes.data
        db.session.commit()
        flash('Aircraft updated successfully.', 'success')
        return redirect(url_for('aircraft.list_aircraft'))

    return render_template('aircraft/form.html', form=form, title='Edit Aircraft')


@bp.route('/<int:aircraft_id>/delete', methods=['POST'])
@login_required
def delete(aircraft_id):
    if current_user.role != 'admin':
        flash('Permission denied.', 'danger')
        return redirect(url_for('aircraft.list_aircraft'))

    ac = db.session.get(Aircraft, aircraft_id)
    if ac:
        db.session.delete(ac)
        db.session.commit()
        flash('Aircraft deleted.', 'success')
    return redirect(url_for('aircraft.list_aircraft'))
