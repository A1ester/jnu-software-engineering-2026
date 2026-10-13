"""Same-origin JSON API. Permissions are enforced on the server, before every write."""
from datetime import date, datetime, time, timedelta, timezone

from flask import Blueprint, g, jsonify, request
from werkzeug.security import check_password_hash

from .db import audit, get_db, iso, notify, transaction
from .security import (create_session, fail, leader, membership, require_active_club,
                       require_leader, require_staff, require_student, require_user, user_json)
from .service import (PUBLIC_STATUSES, activity_json, activity_values, body, boolean,
                      can_read_activity, club_json, decision, get_row, integer,
                      leaders_of, refresh_lifecycle, text, timestamp)

api = Blueprint('api', __name__, url_prefix='/api')


def ok(data, status=200):
    return jsonify(data=data), status


@api.get('/session')
def session():
    if g.auth_session is None:
        with transaction():
            create_session()
    return ok({'user': user_json(), 'csrf_token': g.auth_session['csrf_token']})


@api.post('/login')
def login():
    data = body()
    username = text(data.get('username'), '用户名', 64)
    password = data.get('password')
    if not isinstance(password, str) or not 1 <= len(password) <= 256:
        fail('密码格式不正确。')
    user = get_db().execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
    if user is None or not check_password_hash(user['password_hash'], password):
        fail('用户名或密码错误。', 401, 'invalid_credentials')
    with transaction():
        create_session(user['id'])
        g.user = get_db().execute('SELECT id,username,display_name,role FROM users WHERE id=?', (user['id'],)).fetchone()
    return ok({'user': user_json(), 'csrf_token': g.auth_session['csrf_token']})


@api.post('/logout')
def logout():
    with transaction():
        get_db().execute('DELETE FROM sessions WHERE token_hash=?', (g.auth_session['token_hash'],))
    g.user, g.auth_session, g.clear_cookie = None, None, True
    return ok({'ok': True})


@api.get('/clubs')
def clubs():
    return ok([club_json(row) for row in get_db().execute('SELECT * FROM clubs ORDER BY id')])


@api.get('/clubs/<int:club_id>')
def club_detail(club_id):
    return ok(club_json(get_row('clubs', club_id, '社团')))


@api.get('/my/clubs')
def my_clubs():
    user = require_user()
    result = []
    for row in get_db().execute('SELECT c.*,m.role,m.active FROM clubs c JOIN memberships m ON m.club_id=c.id WHERE m.user_id=? ORDER BY c.id', (user['id'],)):
        data = club_json(row)
        data['active'] = bool(row['active'])
        result.append(data)
    return ok(result)


@api.post('/clubs/<int:club_id>/applications')
def create_application(club_id):
    user = require_student()
    message = text(body().get('message', ''), '申请说明', allow_empty=True)
    with transaction() as connection:
        get_row('clubs', club_id, '社团')
        require_active_club(club_id)
        if membership(club_id) or connection.execute("SELECT 1 FROM applications WHERE club_id=? AND user_id=? AND status='pending'", (club_id, user['id'])).fetchone():
            fail('已经是成员或已有待处理申请。', 409, 'conflict')
        record_id = connection.execute('INSERT INTO applications(club_id,user_id,message,created_at) VALUES(?,?,?,?)', (club_id, user['id'], message, iso())).lastrowid
        for owner in leaders_of(club_id):
            notify(owner, '新入社申请', f'{user["display_name"]}提交了入社申请。')
        audit('application_created', 'application', record_id)
    return ok(dict(get_row('applications', record_id)), 201)


def application_rows(where, args):
    return [dict(row) for row in get_db().execute(
        'SELECT a.id,a.club_id,c.name club_name,a.user_id,u.display_name,a.message,a.status,a.reason FROM applications a JOIN clubs c ON c.id=a.club_id JOIN users u ON u.id=a.user_id WHERE ' + where + ' ORDER BY a.id DESC', args)]


@api.get('/my/applications')
def my_applications():
    return ok(application_rows('a.user_id=?', (require_user()['id'],)))


@api.get('/clubs/<int:club_id>/applications')
def club_applications(club_id):
    require_leader(club_id)
    return ok(application_rows('a.club_id=?', (club_id,)))


@api.post('/applications/<int:application_id>/review')
def review_application(application_id):
    require_user()
    choice, reason = decision(body())
    with transaction() as connection:
        row = get_row('applications', application_id, '入社申请')
        require_leader(row['club_id'], write=True)
        if row['status'] != 'pending':
            fail('该入社申请已处理。', 409, 'invalid_state')
        if choice == 'approve':
            if membership(row['club_id'], row['user_id']):
                fail('申请人已经是有效成员。', 409, 'conflict')
            connection.execute("INSERT INTO memberships(club_id,user_id,role,active,created_at) VALUES(?,?,'member',1,?) ON CONFLICT(club_id,user_id) DO UPDATE SET role='member',active=1", (row['club_id'], row['user_id'], iso()))
        status = 'approved' if choice == 'approve' else 'rejected'
        connection.execute('UPDATE applications SET status=?,reason=?,reviewed_by=?,reviewed_at=? WHERE id=?', (status, reason, g.user['id'], iso(), application_id))
        club = get_row('clubs', row['club_id'])
        notify(row['user_id'], '入社申请结果', f'{club["name"]}：申请' + ('已通过。' if choice == 'approve' else '已驳回。') + reason)
        audit('application_' + status, 'application', application_id, {'reason': reason})
    return ok(dict(get_row('applications', application_id)))


@api.post('/applications/<int:application_id>/cancel')
def cancel_application(application_id):
    user = require_user()
    with transaction() as connection:
        row = get_row('applications', application_id, '入社申请')
        if row['user_id'] != user['id']:
            fail('只能取消本人的入社申请。', 403, 'forbidden')
        if row['status'] != 'pending':
            fail('仅待处理的入社申请可以取消。', 409, 'invalid_state')
        connection.execute("UPDATE applications SET status='cancelled' WHERE id=?", (application_id,))
        audit('application_cancelled', 'application', application_id)
    return ok(dict(get_row('applications', application_id)))


@api.get('/clubs/<int:club_id>/members')
def club_members(club_id):
    user = require_user()
    get_row('clubs', club_id, '社团')
    if user['role'] != 'staff':
        require_leader(club_id)
    result = [dict(row) for row in get_db().execute('SELECT m.id,m.user_id,u.display_name,m.role,m.active FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.club_id=? ORDER BY m.id', (club_id,))]
    for row in result:
        row['active'] = bool(row['active'])
    return ok(result)


@api.patch('/clubs/<int:club_id>/members/<int:membership_id>')
def change_membership(club_id, membership_id):
    require_user()
    active = boolean(body().get('active'), '成员状态')
    with transaction() as connection:
        require_leader(club_id, write=True)
        row = get_row('memberships', membership_id, '成员关系')
        if row['club_id'] != club_id:
            fail('不能修改其他社团的成员。', 403, 'forbidden')
        if row['role'] == 'leader' and not active:
            fail('不能停用现任社团负责人。', 409, 'invalid_state')
        if row['active'] != active:
            connection.execute('UPDATE memberships SET active=? WHERE id=?', (active, membership_id))
            audit('membership_changed', 'membership', membership_id, {'from': bool(row['active']), 'to': bool(active)})
            notify(row['user_id'], '成员状态变更', '社团成员状态已更新。')
    data = dict(get_row('memberships', membership_id))
    data['active'] = bool(data['active'])
    return ok(data)


@api.post('/club-registrations')
def create_club_registration():
    user = require_student()
    data = body()
    name, description = text(data.get('name'), '社团名称', 120), text(data.get('description'), '社团简介')
    with transaction() as connection:
        if connection.execute('SELECT 1 FROM clubs WHERE name=?', (name,)).fetchone() or connection.execute("SELECT 1 FROM club_registrations WHERE name=? AND status='pending'", (name,)).fetchone():
            fail('该名称已有社团或待审备案。', 409, 'conflict')
        record_id = connection.execute('INSERT INTO club_registrations(applicant_id,name,description,created_at) VALUES(?,?,?,?)', (user['id'], name, description, iso())).lastrowid
        for staff in connection.execute("SELECT id FROM users WHERE role='staff'").fetchall():
            notify(staff['id'], '新社团备案', f'{name}的备案申请待审核。')
        audit('club_registration_created', 'club_registration', record_id)
    return ok(dict(get_row('club_registrations', record_id)), 201)


@api.get('/club-registrations')
def club_registrations():
    user = require_user()
    condition, arguments = ('1=1', ()) if user['role'] == 'staff' else ('r.applicant_id=?', (user['id'],))
    return ok([dict(row) for row in get_db().execute('SELECT r.*,u.display_name applicant_name FROM club_registrations r JOIN users u ON u.id=r.applicant_id WHERE ' + condition + ' ORDER BY r.id DESC', arguments)])


@api.post('/club-registrations/<int:registration_id>/review')
def review_club_registration(registration_id):
    user = require_staff()
    choice, reason = decision(body())
    with transaction() as connection:
        row = get_row('club_registrations', registration_id, '社团备案')
        if row['status'] != 'pending':
            fail('备案已经处理。', 409, 'invalid_state')
        club_id = None
        if choice == 'approve':
            if connection.execute('SELECT 1 FROM clubs WHERE name=?', (row['name'],)).fetchone():
                fail('社团名称已经使用。', 409, 'conflict')
            club_id = connection.execute('INSERT INTO clubs(name,description,created_at) VALUES(?,?,?)', (row['name'], row['description'], iso())).lastrowid
            connection.execute("INSERT INTO memberships(club_id,user_id,role,created_at) VALUES(?,?,'leader',?)", (club_id, row['applicant_id'], iso()))
        status = 'approved' if choice == 'approve' else 'rejected'
        connection.execute('UPDATE club_registrations SET status=?,reason=?,reviewed_by=?,reviewed_at=?,club_id=? WHERE id=?', (status, reason, user['id'], iso(), club_id, registration_id))
        notify(row['applicant_id'], '社团备案结果', f'{row["name"]}：' + ('备案已通过。' if choice == 'approve' else '备案已驳回。') + reason)
        audit('club_registration_' + status, 'club_registration', registration_id, {'club_id': club_id, 'reason': reason})
    return ok(dict(get_row('club_registrations', registration_id)))


@api.patch('/clubs/<int:club_id>/governance')
def govern_club(club_id):
    require_staff()
    data = body()
    if not data or any(key not in ('status', 'leader_id') for key in data):
        fail('请提供社团状态或新负责人。')
    if 'status' in data and data['status'] not in ('active', 'disabled'):
        fail('社团状态必须为 active 或 disabled。')
    if 'leader_id' in data:
        integer(data['leader_id'], '新负责人', maximum=2147483647)
    with transaction() as connection:
        row = get_row('clubs', club_id, '社团')
        if 'status' in data and row['status'] != data['status']:
            connection.execute('UPDATE clubs SET status=? WHERE id=?', (data['status'], club_id))
            audit('club_status_changed', 'club', club_id, {'from': row['status'], 'to': data['status']})
            for owner in leaders_of(club_id):
                notify(owner, '社团状态变更', f'{row["name"]}：' + ('已恢复正常。' if data['status'] == 'active' else '已停用。'))
        if 'leader_id' in data:
            new_id = data['leader_id']
            relation = membership(club_id, new_id)
            candidate = get_row('users', new_id, '新负责人')
            if relation is None or candidate['role'] != 'student':
                fail('新负责人必须是该社团的有效学生成员。', 409, 'invalid_state')
            old_owners = leaders_of(club_id)
            if old_owners != [new_id]:
                connection.execute("UPDATE memberships SET role='member' WHERE club_id=? AND role='leader'", (club_id,))
                connection.execute("UPDATE memberships SET role='leader' WHERE id=?", (relation['id'],))
                audit('club_leader_changed', 'club', club_id, {'old_leader_id': old_owners[0] if old_owners else None, 'new_leader_id': new_id})
                for recipient in set(old_owners + [new_id]):
                    notify(recipient, '社团负责人变更', f'{row["name"]}负责人变更已由管理中心确认。')
    return ok(club_json(get_row('clubs', club_id)))


@api.get('/activities')
def activities():
    conditions, arguments = ['a.status IN (' + ','.join('?' for _ in PUBLIC_STATUSES) + ')'], list(PUBLIC_STATUSES)
    for key in ('q', 'theme', 'club_id', 'date'):
        value = request.args.get(key)
        if not value:
            continue
        if key == 'q':
            value = text(value, '搜索内容', 120)
            conditions.append('(instr(a.title,?)>0 OR instr(a.description,?)>0)')
            arguments.extend([value, value])
        elif key == 'theme':
            conditions.append('a.theme=?')
            arguments.append(text(value, '主题', 120))
        elif key == 'club_id':
            try:
                value = int(value)
            except ValueError:
                fail('社团筛选参数必须是整数。')
            conditions.append('a.club_id=?')
            arguments.append(integer(value, '社团', maximum=2147483647))
        else:
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError()
            except ValueError:
                fail('日期筛选格式必须为 YYYY-MM-DD。')
            try:
                offset = int(request.args.get('utc_offset', '0'))
            except ValueError:
                fail('时区偏移必须是整数分钟。')
            integer(offset, '时区偏移', minimum=-840, maximum=840)
            lower = datetime.combine(date.fromisoformat(value), time(), timezone(timedelta(minutes=offset)))
            upper = lower + timedelta(days=1)
            conditions.append('a.start_time>=? AND a.start_time<?')
            arguments.extend([iso(lower), iso(upper)])
    rows = get_db().execute('SELECT a.* FROM activities a WHERE ' + ' AND '.join(conditions) + ' ORDER BY a.start_time,a.id', arguments)
    return ok([activity_json(row) for row in rows])


@api.get('/my/activities')
def my_activities():
    user = require_user()
    if user['role'] == 'staff':
        rows = get_db().execute("SELECT * FROM activities WHERE status='Submitted' ORDER BY id DESC")
    else:
        rows = get_db().execute("SELECT a.* FROM activities a JOIN memberships m ON m.club_id=a.club_id WHERE m.user_id=? AND m.role='leader' AND m.active=1 ORDER BY a.id DESC", (user['id'],))
    return ok([activity_json(row) for row in rows])


@api.get('/activities/<int:activity_id>')
def activity_detail(activity_id):
    row = get_row('activities', activity_id, '活动')
    if not can_read_activity(row):
        fail('活动不存在或尚未公开。', 404, 'not_found')
    return ok(activity_json(row, detail=True))


@api.post('/activities')
def create_activity():
    require_user()
    values = activity_values(body())
    with transaction() as connection:
        get_row('clubs', values['club_id'], '社团')
        require_leader(values['club_id'], write=True)
        columns = ','.join(values)
        record_id = connection.execute('INSERT INTO activities(' + columns + ',created_by,created_at) VALUES(' + ','.join('?' for _ in values) + ',?,?)', (*values.values(), g.user['id'], iso())).lastrowid
        audit('activity_created', 'activity', record_id)
    return ok(activity_json(get_row('activities', record_id)), 201)


@api.patch('/activities/<int:activity_id>')
def edit_activity(activity_id):
    require_user()
    data = body()
    if not data:
        fail('请提供要修改的活动信息。')
    with transaction() as connection:
        row = get_row('activities', activity_id, '活动')
        require_leader(row['club_id'], write=True)
        if row['status'] not in ('Draft', 'Rejected'):
            fail('只有草稿或驳回的活动可以编辑。', 409, 'invalid_state')
        values = activity_values(data, row)
        connection.execute('UPDATE activities SET ' + ','.join(key + '=?' for key in values) + ",status='Draft',review_reason='' WHERE id=?", (*values.values(), activity_id))
        audit('activity_edited', 'activity', activity_id, {'from': row['status'], 'to': 'Draft'})
    return ok(activity_json(get_row('activities', activity_id)))


@api.post('/activities/<int:activity_id>/transition')
def transition_activity(activity_id):
    require_user()
    data = body()
    action = data.get('action')
    if action not in ('submit', 'approve', 'reject', 'publish', 'open_registration', 'cancel', 'archive'):
        fail('活动操作无效。')
    reason = text(data.get('reason', ''), '操作原因', allow_empty=action != 'reject')
    with transaction() as connection:
        refresh_lifecycle(connection)
        row = get_row('activities', activity_id, '活动')
        if action in ('approve', 'reject'):
            require_staff()
            require_active_club(row['club_id'])
        else:
            require_leader(row['club_id'], write=True)
        allowed = {'submit': ('Draft',), 'approve': ('Submitted',), 'reject': ('Submitted',),
                   'publish': ('Approved',), 'open_registration': ('Published',),
                   'cancel': ('Published', 'RegistrationOpen', 'RegistrationClosed'), 'archive': ('Finished',)}
        if row['status'] not in allowed[action]:
            fail('当前活动状态不允许此操作。', 409, 'invalid_state')
        if action in ('submit', 'publish', 'open_registration') and iso() >= row['registration_deadline']:
            fail('报名截止时间已到，不能提交、发布或开启报名。', 409, 'deadline_passed')
        if action == 'cancel' and iso() >= row['start_time']:
            fail('活动开始后不能取消。', 409, 'invalid_state')
        target = {'submit': 'Submitted', 'approve': 'Approved', 'reject': 'Rejected', 'publish': 'Published',
                  'open_registration': 'RegistrationOpen', 'cancel': 'Cancelled', 'archive': 'Archived'}[action]
        connection.execute('UPDATE activities SET status=?,review_reason=? WHERE id=?', (target, reason if action == 'reject' else row['review_reason'], activity_id))
        audit('activity_' + action, 'activity', activity_id, {'from': row['status'], 'to': target, 'reason': reason})
        if action in ('approve', 'reject'):
            for owner in leaders_of(row['club_id']):
                notify(owner, '活动审核结果', f'{row["title"]}：' + ('审核已通过。' if action == 'approve' else '审核已驳回。') + reason)
        elif action == 'submit':
            for staff in connection.execute("SELECT id FROM users WHERE role='staff'").fetchall():
                notify(staff['id'], '活动待审核', f'{row["title"]}已提交审核。')
        elif action == 'cancel':
            for record in connection.execute("SELECT DISTINCT user_id FROM registrations WHERE activity_id=? AND status IN ('confirmed','waitlisted')", (activity_id,)).fetchall():
                notify(record['user_id'], '活动取消', f'{row["title"]}已取消。{reason}')
    return ok(activity_json(get_row('activities', activity_id)))


@api.post('/activities/<int:activity_id>/registrations')
def register_activity(activity_id):
    user = require_student()
    with transaction() as connection:
        refresh_lifecycle(connection)
        row = get_row('activities', activity_id, '活动')
        require_active_club(row['club_id'])
        if row['status'] != 'RegistrationOpen' or iso() >= row['registration_deadline']:
            fail('活动尚未开启报名或已经截止。', 409, 'invalid_state')
        if connection.execute("SELECT 1 FROM registrations WHERE activity_id=? AND user_id=? AND status IN ('confirmed','waitlisted')", (activity_id, user['id'])).fetchone():
            fail('已经报名或候补，请勿重复提交。', 409, 'conflict')
        count = connection.execute("SELECT COUNT(*) FROM registrations WHERE activity_id=? AND status='confirmed'", (activity_id,)).fetchone()[0]
        if count >= row['capacity'] and not row['waitlist_enabled']:
            fail('活动报名已满。', 409, 'capacity_full')
        status = 'waitlisted' if count >= row['capacity'] else 'confirmed'
        record_id = connection.execute('INSERT INTO registrations(activity_id,user_id,status,created_at) VALUES(?,?,?,?)', (activity_id, user['id'], status, iso())).lastrowid
        notify(user['id'], '报名结果', f'{row["title"]}：' + ('已正式报名。' if status == 'confirmed' else '已进入候补队列。'))
        audit('registration_' + status, 'registration', record_id)
    data = dict(get_row('registrations', record_id))
    data['checked_in'] = bool(data['checked_in'])
    return ok(data, 201)


@api.get('/my/registrations')
def my_registrations():
    user = require_user()
    result = [dict(row) for row in get_db().execute('SELECT r.id,r.activity_id,a.title,r.status,r.checked_in,a.start_time,a.location,a.status activity_status FROM registrations r JOIN activities a ON a.id=r.activity_id WHERE r.user_id=? ORDER BY r.id DESC', (user['id'],))]
    for row in result:
        row['checked_in'] = bool(row['checked_in'])
    return ok(result)


@api.post('/registrations/<int:registration_id>/cancel')
def cancel_registration(registration_id):
    user = require_user()
    with transaction() as connection:
        refresh_lifecycle(connection)
        row = get_row('registrations', registration_id, '报名')
        if row['user_id'] != user['id']:
            fail('只能取消本人的报名。', 403, 'forbidden')
        activity = get_row('activities', row['activity_id'])
        if row['status'] not in ('confirmed', 'waitlisted') or row['checked_in']:
            fail('此报名无法取消。', 409, 'invalid_state')
        if iso() >= activity['registration_deadline']:
            fail('报名截止时间已到，不能自行取消。', 409, 'deadline_passed')
        connection.execute("UPDATE registrations SET status='cancelled',cancelled_at=? WHERE id=?", (iso(), registration_id))
        notify(user['id'], '报名取消', f'{activity["title"]}：已取消报名或候补。')
        audit('registration_cancelled', 'registration', registration_id)
        if row['status'] == 'confirmed' and activity['status'] == 'RegistrationOpen' and activity['waitlist_enabled'] and iso() < activity['registration_deadline']:
            # Disabled clubs preserve personal cancellation rights but do not advance their waitlist.
            club = get_row('clubs', activity['club_id'])
            if club['status'] == 'active':
                first = connection.execute("SELECT * FROM registrations WHERE activity_id=? AND status='waitlisted' ORDER BY id LIMIT 1", (activity['id'],)).fetchone()
                if first:
                    connection.execute("UPDATE registrations SET status='confirmed' WHERE id=?", (first['id'],))
                    notify(first['user_id'], '候补转正', f'{activity["title"]}：候补已转为正式报名。')
                    audit('waitlist_promoted', 'registration', first['id'])
    result = dict(get_row('registrations', registration_id))
    result['checked_in'] = bool(result['checked_in'])
    return ok(result)


@api.get('/activities/<int:activity_id>/registrations')
def activity_registrations(activity_id):
    require_user()
    row = get_row('activities', activity_id, '活动')
    if not leader(row['club_id']) and not (row['status'] == 'InProgress' and membership(row['club_id'])):
        fail('仅所属负责人或进行中活动的有效组织成员可查看签到名单。', 403, 'forbidden')
    records = [dict(item) for item in get_db().execute('SELECT r.id,r.user_id,u.display_name,r.status,r.checked_in FROM registrations r JOIN users u ON u.id=r.user_id WHERE r.activity_id=? ORDER BY r.id', (activity_id,))]
    for record in records:
        record['checked_in'] = bool(record['checked_in'])
    return ok(records)


@api.post('/activities/<int:activity_id>/check-ins')
def check_in(activity_id):
    require_user()
    user_id = integer(body().get('user_id'), '签到学生', maximum=2147483647)
    with transaction() as connection:
        refresh_lifecycle(connection)
        activity = get_row('activities', activity_id, '活动')
        require_active_club(activity['club_id'])
        if membership(activity['club_id']) is None:
            fail('签到需要该社团有效组织成员权限。', 403, 'forbidden')
        if activity['status'] != 'InProgress':
            fail('只有进行中的活动可以签到。', 409, 'invalid_state')
        row = connection.execute("SELECT * FROM registrations WHERE activity_id=? AND user_id=? AND status='confirmed'", (activity_id, user_id)).fetchone()
        if row is None or row['checked_in']:
            fail('学生未正式报名或已经签到。', 409, 'invalid_state')
        connection.execute('UPDATE registrations SET checked_in=1,checked_in_at=? WHERE id=?', (iso(), row['id']))
        notify(user_id, '签到成功', f'{activity["title"]}：已签到。')
        audit('check_in_recorded', 'registration', row['id'])
    result = dict(get_row('registrations', row['id']))
    result['checked_in'] = bool(result['checked_in'])
    return ok(result)


@api.get('/tasks')
def tasks():
    user = require_user()
    rows = get_db().execute("SELECT t.*,a.title activity_title,a.club_id,u.display_name assignee_name FROM tasks t JOIN activities a ON a.id=t.activity_id JOIN users u ON u.id=t.assignee_id WHERE EXISTS (SELECT 1 FROM memberships m WHERE m.club_id=a.club_id AND m.user_id=? AND m.active=1 AND (m.role='leader' OR t.assignee_id=?)) ORDER BY t.due_time,t.id", (user['id'], user['id']))
    return ok([dict(row) for row in rows])


@api.post('/activities/<int:activity_id>/tasks')
def create_task(activity_id):
    require_user()
    data = body()
    title = text(data.get('title'), '任务标题', 120)
    assignee_id = integer(data.get('assignee_id'), '任务担当人', maximum=2147483647)
    due_time = timestamp(data.get('due_time'), '任务截止时间')
    with transaction() as connection:
        activity = get_row('activities', activity_id, '活动')
        require_leader(activity['club_id'], write=True)
        if activity['status'] in ('Cancelled', 'Finished', 'Archived'):
            fail('已结束、取消或归档的活动不能新增筹备任务。', 409, 'invalid_state')
        if membership(activity['club_id'], assignee_id) is None:
            fail('任务担当人必须是该社团有效成员。', 409, 'invalid_state')
        record_id = connection.execute('INSERT INTO tasks(activity_id,title,assignee_id,due_time,created_at) VALUES(?,?,?,?,?)', (activity_id, title, assignee_id, due_time, iso())).lastrowid
        notify(assignee_id, '任务分配', f'{activity["title"]}：{title}，截止时间 {due_time}。')
        audit('task_created', 'task', record_id)
    return ok(dict(get_row('tasks', record_id)), 201)


@api.patch('/tasks/<int:task_id>')
def update_task(task_id):
    user = require_user()
    status = body().get('status')
    if status not in ('todo', 'in_progress', 'done'):
        fail('任务状态无效。')
    with transaction() as connection:
        row = get_row('tasks', task_id, '任务')
        activity = get_row('activities', row['activity_id'])
        require_active_club(activity['club_id'])
        if not leader(activity['club_id']) and not (row['assignee_id'] == user['id'] and membership(activity['club_id'])):
            fail('只能更新本人任务或本人负责社团的任务。', 403, 'forbidden')
        if activity['status'] in ('Cancelled', 'Archived'):
            fail('取消或归档活动的任务不能更改。', 409, 'invalid_state')
        if row['status'] == 'done' and status != 'done':
            fail('完成的任务不能退回未完成状态。', 409, 'invalid_state')
        if status != row['status'] and status != {'todo': 'in_progress', 'in_progress': 'done'}.get(row['status']):
            fail('任务需依次从待办进入进行中，再标记完成。', 409, 'invalid_state')
        if status != row['status']:
            connection.execute('UPDATE tasks SET status=? WHERE id=?', (status, task_id))
            audit('task_status_changed', 'task', task_id, {'from': row['status'], 'to': status})
    return ok(dict(get_row('tasks', task_id)))


@api.get('/notifications')
def notifications():
    user = require_user()
    records = [dict(row) for row in get_db().execute('SELECT id,title,message,read,created_at FROM notifications WHERE user_id=? ORDER BY id DESC', (user['id'],))]
    for row in records:
        row['read'] = bool(row['read'])
    return ok(records)


@api.post('/notifications/<int:notification_id>/read')
def read_notification(notification_id):
    user = require_user()
    with transaction() as connection:
        row = get_row('notifications', notification_id, '通知')
        if row['user_id'] != user['id']:
            fail('只能读取本人的通知。', 403, 'forbidden')
        connection.execute('UPDATE notifications SET read=1 WHERE id=?', (notification_id,))
    return ok({'ok': True})


@api.get('/audit')
def audit_records():
    require_staff()
    return ok([dict(row) for row in get_db().execute("SELECT a.id,COALESCE(u.display_name,'系统') actor_name,a.action,a.entity_type,a.entity_id,a.details,a.created_at FROM audit_events a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 500")])


@api.get('/logs')
def logs():
    require_staff()
    return ok([dict(row) for row in get_db().execute('SELECT * FROM runtime_logs ORDER BY id DESC LIMIT 500')])
