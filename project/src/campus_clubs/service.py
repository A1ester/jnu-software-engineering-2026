"""Shared validation and lifecycle rules used by HTTP requests and the clock command."""
from datetime import datetime, timezone

from flask import g, request

from .db import audit, get_db, iso, now, runtime_log, transaction
from .security import fail, leader

PUBLIC_STATUSES = ('Published', 'RegistrationOpen', 'RegistrationClosed', 'InProgress', 'Finished', 'Archived', 'Cancelled')


def body():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        fail('请提交 JSON 对象。', 400, 'invalid_json')
    return value


def text(value, label, maximum=2000, allow_empty=False):
    if not isinstance(value, str):
        fail(f'{label}必须是文本。')
    value = value.strip()
    if (not allow_empty and not value) or len(value) > maximum:
        fail(f'{label}不能为空，且最多 {maximum} 个字符。' if not allow_empty else f'{label}最多 {maximum} 个字符。')
    return value


def integer(value, label, minimum=1, maximum=10000):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        fail(f'{label}必须是 {minimum} 到 {maximum} 之间的整数。')
    return value


def boolean(value, label):
    if not isinstance(value, bool):
        fail(f'{label}必须是布尔值。')
    return int(value)


def timestamp(value, label):
    if not isinstance(value, str) or len(value) > 64:
        fail(f'{label}必须是带时区的 ISO 8601 时间。')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError()
        return iso(parsed.astimezone(timezone.utc))
    except (ValueError, OverflowError):
        fail(f'{label}必须是带时区的有效 ISO 8601 时间。')


def get_row(table, row_id, label='记录'):
    row = get_db().execute(f'SELECT * FROM {table} WHERE id=?', (row_id,)).fetchone()
    if row is None:
        fail(f'{label}不存在。', 404, 'not_found')
    return row


def decision(data):
    choice = data.get('decision')
    if choice not in ('approve', 'reject'):
        fail('审核结论必须为 approve 或 reject。')
    reason = text(data.get('reason', ''), '审核原因', allow_empty=choice == 'approve')
    return choice, reason


def activity_values(data, existing=None):
    allowed = ('club_id', 'title', 'theme', 'description', 'location', 'capacity', 'registration_deadline', 'start_time', 'end_time', 'waitlist_enabled')
    if any(key not in allowed for key in data):
        fail('活动信息包含未知字段。')
    values = dict(existing) if existing else {}
    values.update(data)
    result = {
        'club_id': integer(values.get('club_id'), '社团', maximum=2147483647),
        'title': text(values.get('title'), '活动标题', 120),
        'theme': text(values.get('theme'), '活动主题', 120),
        'description': text(values.get('description'), '活动说明'),
        'location': text(values.get('location'), '活动地点', 120),
        'capacity': integer(values.get('capacity'), '活动容量'),
    }
    for field, label in (('registration_deadline', '报名截止时间'), ('start_time', '活动开始时间'), ('end_time', '活动结束时间')):
        result[field] = timestamp(values.get(field), label)
    if not result['registration_deadline'] <= result['start_time'] < result['end_time']:
        fail('报名截止时间必须不晚于开始时间，开始时间必须早于结束时间。')
    waitlist = values.get('waitlist_enabled', False)
    if existing is not None and 'waitlist_enabled' not in data:
        waitlist = bool(waitlist)
    result['waitlist_enabled'] = boolean(waitlist, '候补开关')
    if existing and result['club_id'] != existing['club_id']:
        fail('活动所属社团不能更改。')
    return result


def club_json(row):
    result = dict(row)
    result['leader_name'] = get_db().execute(
        "SELECT u.display_name FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.club_id=? AND m.role='leader' AND m.active=1", (row['id'],)).fetchone()
    result['leader_name'] = result['leader_name'][0] if result['leader_name'] else None
    return result


def activity_json(row, detail=False):
    result = {key: row[key] for key in ('id', 'club_id', 'title', 'theme', 'description', 'location', 'capacity', 'registration_deadline', 'start_time', 'end_time', 'waitlist_enabled', 'status', 'review_reason')}
    result['waitlist_enabled'] = bool(result['waitlist_enabled'])
    result['club_name'] = get_db().execute('SELECT name FROM clubs WHERE id=?', (row['club_id'],)).fetchone()[0]
    counts = dict((record['status'], record['total']) for record in get_db().execute(
        'SELECT status,COUNT(*) total FROM registrations WHERE activity_id=? GROUP BY status', (row['id'],)))
    result['registered_count'] = counts.get('confirmed', 0)
    result['waitlist_count'] = counts.get('waitlisted', 0)
    if detail:
        registration = get_db().execute('SELECT id,status,checked_in FROM registrations WHERE activity_id=? AND user_id=? ORDER BY id DESC LIMIT 1',
                                        (row['id'], g.user['id'] if g.user else None)).fetchone()
        result['my_registration'] = dict(registration) if registration else None
        if registration:
            result['my_registration']['checked_in'] = bool(registration['checked_in'])
        feedback = get_db().execute('SELECT rating,comment FROM feedback WHERE activity_id=? AND user_id=?',
                                    (row['id'], g.user['id'] if g.user else None)).fetchone()
        result['my_feedback'] = dict(feedback) if feedback else None
    return result


def refresh_lifecycle(connection=None):
    """Caller holds a write transaction. Only already published states advance."""
    connection = connection or get_db()
    instant = iso()
    rows = connection.execute("SELECT * FROM activities WHERE status IN ('Published','RegistrationOpen','RegistrationClosed','InProgress') ORDER BY id").fetchall()
    transitions = []
    for row in rows:
        status = row['status']
        if status in ('Published', 'RegistrationOpen') and instant >= row['registration_deadline']:
            transitions.append((row['id'], status, 'RegistrationClosed'))
            status = 'RegistrationClosed'
        if status == 'RegistrationClosed' and instant >= row['start_time']:
            transitions.append((row['id'], status, 'InProgress'))
            status = 'InProgress'
        if status == 'InProgress' and instant >= row['end_time']:
            transitions.append((row['id'], status, 'Finished'))
    for activity_id, old, new in transitions:
        connection.execute('UPDATE activities SET status=? WHERE id=?', (new, activity_id))
        # Automatic time changes are attributed to the system, even during a student's request.
        connection.execute('INSERT INTO audit_events(actor_id,action,entity_type,entity_id,details,created_at) VALUES(NULL,?,?,?,?,?)',
                           ('lifecycle_advance', 'activity', activity_id, '{"from":"' + old + '","to":"' + new + '"}', instant))
    return len(transitions)


def tick():
    try:
        with transaction() as connection:
            return refresh_lifecycle(connection)
    except Exception:
        with transaction():
            runtime_log('background_task_failure', 'failed', '活动生命周期刷新失败。')
        raise


def leaders_of(club_id):
    return [row[0] for row in get_db().execute("SELECT user_id FROM memberships WHERE club_id=? AND role='leader' AND active=1", (club_id,))]


def can_read_activity(row):
    return row['status'] in PUBLIC_STATUSES or (g.user and (g.user['role'] == 'staff' or leader(row['club_id'])))
