"""Automatic weekly schedule via integer linear programming (PuLP / CBC).

The matching problem: several students request overlapping time slots but there are
limited aircraft and instructors. We pick which student flies which hour so that:
  - a student only flies hours they marked available (and isn't already booked),
  - each hour uses no more flights than there are free aircraft AND free instructors,
  - no student exceeds their requested hours,
maximising a FAIRNESS-weighted objective (each student's first hours are worth the
most, so the solver spreads hours across people instead of loading up one student).
Instructors/aircraft are interchangeable here, so they're assigned per hour after the
LP (with a preference to keep the same resource across a contiguous block).
"""
from collections import defaultdict
import pulp


def solve(students, instructors, aircraft, busy, hours, split_ids=None, distribute_week=True):
    """Return a set of (student_id, date_iso, hour) chosen to be flown.

    students: [{id, avail: set((date_iso, hour)), need: int}]
    instructors / aircraft: lists of ids
    busy: {'instr': set((id,date,hour)), 'plane': set((id,date,hour)), 'student': set((id,date,hour))}
    hours: list of grid hour ints
    """
    prob = pulp.LpProblem('weekly_schedule', pulp.LpMaximize)
    x = {}
    for s in students:
        if int(s['need'] + 1e-9) <= 0:        # floor: never schedule more than requested
            continue
        for (d, h) in s['avail']:
            if (s['id'], d, h) in busy['student']:
                continue
            x[(s['id'], d, h)] = pulp.LpVariable(f"x_{s['id']}_{d}_{h}", cat='Binary')

    # Capacity per (date, hour): at most min(free instructors, free aircraft) flights.
    slot_vars = defaultdict(list)
    for (sid, d, h), var in x.items():
        slot_vars[(d, h)].append(var)
    for (d, h), lst in slot_vars.items():
        free_instr = len(instructors) - sum(1 for i in instructors if (i, d, h) in busy['instr'])
        free_ac = len(aircraft) - sum(1 for a in aircraft if (a, d, h) in busy['plane'])
        prob += pulp.lpSum(lst) <= max(0, min(free_instr, free_ac))

    objective = []
    for s in students:
        need = int(s['need'] + 1e-9)          # floor — don't exceed requested hours
        if need <= 0:
            continue
        svars = [x[(s['id'], d, h)] for (d, h) in s['avail'] if (s['id'], d, h) in x]
        if not svars:
            continue
        prob += pulp.lpSum(svars) <= need
        # Fairness: split the need into tiers with decreasing reward (first hour ~100).
        tiers = [pulp.LpVariable(f"t_{s['id']}_{m}", cat='Binary') for m in range(need)]
        prob += pulp.lpSum(svars) == pulp.lpSum(tiers)
        for m in range(1, need):
            prob += tiers[m] <= tiers[m - 1]
        for m in range(need):
            objective.append(round(100 * (need - m) / need) * tiers[m])

    # Per-student soft preference for contiguous hours (skip students who allow splitting).
    split_ids = set(split_ids or [])
    for s in students:
        if s['id'] in split_ids:
            continue
        days = {d for (d, _h) in s['avail']}
        for d in days:
            for h in hours:
                a = x.get((s['id'], d, h))
                b = x.get((s['id'], d, h + 1))
                if a is not None and b is not None:
                    c = pulp.LpVariable(f"c_{s['id']}_{d}_{h}", cat='Binary')
                    prob += c <= a
                    prob += c <= b
                    objective.append(8 * c)

    # Spread flights across the week by minimising the busiest day's load.
    if distribute_week:
        day_loads = defaultdict(list)
        for (sid, d, h), var in x.items():
            day_loads[d].append(var)
        if day_loads:
            peak = pulp.LpVariable('peak_day', lowBound=0)
            for d, vs in day_loads.items():
                prob += peak >= pulp.lpSum(vs)
            objective.append(-5 * peak)

    prob += pulp.lpSum(objective)
    prob.solve(pulp.PULP_CBC_CMD(msg=0))

    chosen = set()
    if pulp.LpStatus[prob.status] in ('Optimal', 'Not Solved'):
        for (sid, d, h), var in x.items():
            val = var.value()
            if val is not None and val > 0.5:
                chosen.add((sid, d, h))
    return chosen


def assign_resources(chosen, instructors, aircraft, busy, distribute=True):
    """Assign an instructor + aircraft to each chosen hour. Keeps the same resource
    across a student's consecutive hours (blocks). When `distribute` is set, new blocks
    go to the LEAST-USED free aircraft/instructor so flights spread across the fleet;
    otherwise they pack onto the first free one.
    Returns {(sid,date,hour): (instr_id, aircraft_id)}."""
    by_slot = defaultdict(list)
    for (sid, d, h) in chosen:
        by_slot[(d, h)].append(sid)

    instr_busy = set(busy['instr'])
    ac_busy = set(busy['plane'])
    instr_load = {i: 0 for i in instructors}
    ac_load = {a: 0 for a in aircraft}
    for (i, _d, _h) in busy['instr']:
        if i in instr_load:
            instr_load[i] += 1
    for (a, _d, _h) in busy['plane']:
        if a in ac_load:
            ac_load[a] += 1

    prev = {}        # sid -> (date, hour, instr, ac)
    out = {}
    for (d, h) in sorted(by_slot):
        for sid in by_slot[(d, h)]:
            ci = ca = None
            p = prev.get(sid)
            if p and p[0] == d and p[1] == h - 1:           # continue the block on the same resource
                if (p[2], d, h) not in instr_busy:
                    ci = p[2]
                if (p[3], d, h) not in ac_busy:
                    ca = p[3]
            if ci is None:
                free = [i for i in instructors if (i, d, h) not in instr_busy]
                ci = (min(free, key=lambda i: instr_load[i]) if distribute else free[0]) if free else None
            if ca is None:
                free = [a for a in aircraft if (a, d, h) not in ac_busy]
                ca = (min(free, key=lambda a: ac_load[a]) if distribute else free[0]) if free else None
            if ci is None or ca is None:
                continue
            instr_busy.add((ci, d, h))
            ac_busy.add((ca, d, h))
            instr_load[ci] += 1
            ac_load[ca] += 1
            out[(sid, d, h)] = (ci, ca)
            prev[sid] = (d, h, ci, ca)
    return out


def group_flights(assignment, student_types):
    """Group consecutive same-student/instructor/aircraft/type hours into flight dicts.

    assignment: {(sid,date,hour): (instr, ac)}
    student_types: {sid: [hour_type, ...]}  — ordered type quota to consume per hour
    """
    # assign a type to each (sid, date, hour) in chronological order
    per_student = defaultdict(list)
    for (sid, d, h), (i, a) in assignment.items():
        per_student[sid].append((d, h, i, a))

    typed = {}
    for sid, slots in per_student.items():
        slots.sort()
        types = list(student_types.get(sid) or [])
        for idx, (d, h, i, a) in enumerate(slots):
            t = types[idx] if idx < len(types) else (types[-1] if types else 'PPL-A')
            typed[(sid, d, h)] = (i, a, t)

    flights = []
    for sid, slots in per_student.items():
        slots.sort()
        cur = None
        for (d, h, i, a) in slots:
            ti, ta, tt = typed[(sid, d, h)]
            if cur and cur['date'] == d and cur['_endh'] == h and cur['instructor_id'] == ti \
                    and cur['aircraft_id'] == ta and cur['hour_type'] == tt:
                cur['_endh'] = h + 1
            else:
                if cur:
                    flights.append(_finish(cur))
                cur = {'student_id': sid, 'date': d, '_starth': h, '_endh': h + 1,
                       'instructor_id': ti, 'aircraft_id': ta, 'hour_type': tt}
        if cur:
            flights.append(_finish(cur))
    return flights


def _finish(c):
    return {
        'student_id': c['student_id'], 'date': c['date'],
        'start': f"{c['_starth']:02d}:00", 'end': f"{c['_endh']:02d}:00",
        'instructor_id': c['instructor_id'], 'aircraft_id': c['aircraft_id'],
        'hour_type': c['hour_type'],
    }
