from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from app import db
from app.models import User, Aircraft, Booking
from app.forms import BookingForm

bp = Blueprint('scheduling', __name__, url_prefix='/schedule')


@bp.route('/')
@login_required
def calendar():
    instructors = User.query.filter_by(role='instructor', is_active=True).all()
    aircraft_list = Aircraft.query.filter_by(is_available=True).all()
    return render_template('scheduling/calendar.html', instructors=instructors, aircraft=aircraft_list)


@bp.route('/api/events')
@login_required
def events():
    start = request.args.get('start')
    end = request.args.get('end')

    query = Booking.query.filter(Booking.status != 'cancelled')

    if start:
        query = query.filter(Booking.start_time >= datetime.fromisoformat(start))
    if end:
        query = query.filter(Booking.end_time <= datetime.fromisoformat(end))

    if current_user.role == 'student':
        query = query.filter(Booking.student_id == current_user.id)
    elif current_user.role == 'instructor':
        query = query.filter(
            db.or_(Booking.instructor_id == current_user.id, Booking.student_id == current_user.id)
        )

    bookings = query.all()
    events = []
    colors = {
        'training': '#0d6efd',
        'solo': '#198754',
        'checkride': '#dc3545',
        'intro': '#6f42c1',
    }
    for b in bookings:
        events.append({
            'id': b.id,
            'title': f'{b.aircraft.registration} - {b.student.full_name}',
            'start': b.start_time.isoformat(),
            'end': b.end_time.isoformat(),
            'color': colors.get(b.flight_type, '#0d6efd'),
            'extendedProps': {
                'instructor': b.instructor.full_name,
                'student': b.student.full_name,
                'aircraft': f'{b.aircraft.registration} ({b.aircraft.model})',
                'flight_type': b.flight_type,
                'status': b.status,
                'notes': b.notes or '',
            }
        })
    return jsonify(events)


@bp.route('/book', methods=['GET', 'POST'])
@login_required
def book():
    form = BookingForm()

    aircraft_list = Aircraft.query.filter_by(is_available=True).all()
    instructors = User.query.filter_by(role='instructor', is_active=True).all()
    students = User.query.filter_by(role='student', is_active=True).all()

    form.aircraft_id.choices = [(a.id, f'{a.registration} - {a.model}') for a in aircraft_list]
    form.instructor_id.choices = [(i.id, i.full_name) for i in instructors]

    if current_user.role == 'student':
        form.student_id.choices = [(current_user.id, current_user.full_name)]
    else:
        form.student_id.choices = [(s.id, s.full_name) for s in students]

    if form.validate_on_submit():
        if current_user.role == 'student' and form.student_id.data != current_user.id:
            flash('You can only book flights for yourself.', 'danger')
            return render_template('scheduling/book.html', form=form)

        if form.start_time.data >= form.end_time.data:
            flash('End time must be after start time.', 'danger')
            return render_template('scheduling/book.html', form=form)

        conflict = Booking.has_conflict(
            aircraft_id=form.aircraft_id.data,
            instructor_id=form.instructor_id.data,
            student_id=form.student_id.data,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
        )
        if conflict:
            flash(conflict, 'danger')
            return render_template('scheduling/book.html', form=form)

        booking = Booking(
            student_id=form.student_id.data,
            instructor_id=form.instructor_id.data,
            aircraft_id=form.aircraft_id.data,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            flight_type=form.flight_type.data,
            notes=form.notes.data,
        )
        db.session.add(booking)
        db.session.commit()
        flash('Flight booked successfully!', 'success')
        return redirect(url_for('scheduling.calendar'))

    return render_template('scheduling/book.html', form=form)


@bp.route('/my-bookings')
@login_required
def my_bookings():
    if current_user.role == 'student':
        bookings = Booking.query.filter_by(student_id=current_user.id).order_by(Booking.start_time.desc()).all()
    elif current_user.role == 'instructor':
        bookings = Booking.query.filter_by(instructor_id=current_user.id).order_by(Booking.start_time.desc()).all()
    else:
        bookings = Booking.query.order_by(Booking.start_time.desc()).all()
    return render_template('scheduling/my_bookings.html', bookings=bookings)


@bp.route('/<int:booking_id>/cancel', methods=['POST'])
@login_required
def cancel(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking:
        flash('Booking not found.', 'danger')
        return redirect(url_for('scheduling.my_bookings'))

    if current_user.role == 'student' and booking.student_id != current_user.id:
        flash('You can only cancel your own bookings.', 'danger')
        return redirect(url_for('scheduling.my_bookings'))

    booking.status = 'cancelled'
    db.session.commit()
    flash('Booking cancelled.', 'success')
    return redirect(url_for('scheduling.my_bookings'))
