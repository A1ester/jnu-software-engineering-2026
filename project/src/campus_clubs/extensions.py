"""Resource coordination, personal feedback, governance reports, and aggregate statistics."""
import csv
import io

from flask import Blueprint, Response, g, request

from .db import audit, get_db, iso, notify, transaction
from .routes import ok
from .security import (fail, leader, require_active_club, require_leader,
                       require_staff, require_student, require_user)
from .service import (PUBLIC_STATUSES, activity_json, body, decision, get_row,
                      integer, leaders_of, refresh_lifecycle, text, timestamp)

extensions = Blueprint('extensions', __name__, url_prefix='/api')
VENUE_ACTIVITY_STATUSES = ('Submitted', 'Approved', 'Published', 'RegistrationOpen', 'RegistrationClosed', 'InProgress')


def staff_or_leader(club_id):
    user = require_user()
    if user['role'] != 'staff':
        require_leader(club_id)


def require_any_leader():
    user = require_user()
    if user['role'] == 'staff':
        return
    if not get_db().execute("SELECT 1 FROM memberships WHERE user_id=? AND role='leader' AND active=1", (user['id'],)).fetchone():
        fail('需要所属社团负责人或学校社团管理中心工作人员权限。', 403, 'forbidden')


@extensions.get('/todos')
def todos():
    user = require_user()
    connection = get_db()
    result = []
    tasks = connection.execute("SELECT t.id,t.title,t.due_time,t.activity_id,a.club_id FROM tasks t JOIN activities a ON a.id=t.activity_id JOIN clubs c ON c.id=a.club_id WHERE t.status!='done' AND c.status='active' AND a.status NOT IN ('Cancelled','Archived') AND EXISTS(SELECT 1 FROM memberships m WHERE m.club_id=a.club_id AND m.user_id=? AND m.active=1 AND (m.role='leader' OR t.assignee_id=?))", (user['id'], user['id']))
    for row in tasks:
        result.append({'kind': 'task', 'id': row['id'], 'title': row['title'], 'deadline': row['due_time'], 'activity_id': row['activity_id'], 'club_id': row['club_id']})
    applications = connection.execute("SELECT a.id,a.club_id,c.name,u.display_name FROM applications a JOIN clubs c ON c.id=a.club_id JOIN users u ON u.id=a.user_id WHERE a.status='pending' AND c.status='active' AND EXISTS(SELECT 1 FROM memberships m WHERE m.club_id=a.club_id AND m.user_id=? AND m.role='leader' AND m.active=1)", (user['id'],))
    for row in applications:
        result.append({'kind': 'application', 'id': row['id'], 'title': f'{row["name"]}：{row["display_name"]}的入社申请', 'deadline': None, 'club_id': row['club_id']})
    if user['role'] == 'staff':
        for row in connection.execute("SELECT a.id,a.title,a.club_id,a.registration_deadline FROM activities a JOIN clubs c ON c.id=a.club_id WHERE a.status='Submitted' AND c.status='active'"):
            result.append({'kind': 'activity', 'id': row['id'], 'title': '活动审核：' + row['title'], 'deadline': row['registration_deadline'], 'activity_id': row['id'], 'club_id': row['club_id']})
        for row in connection.execute("SELECT id,name FROM club_registrations WHERE status='pending'"):
            result.append({'kind': 'club_registration', 'id': row['id'], 'title': '社团备案审核：' + row['name'], 'deadline': None})
        for row in connection.execute("SELECT v.id,v.activity_id,v.start_time,a.title,a.club_id FROM venue_applications v JOIN activities a ON a.id=v.activity_id WHERE v.status='pending'"):
            result.append({'kind': 'venue_application', 'id': row['id'], 'title': '场地申请审核：' + row['title'], 'deadline': row['start_time'], 'activity_id': row['activity_id'], 'club_id': row['club_id']})
        for row in connection.execute("SELECT r.id,r.activity_id,a.title,a.club_id FROM reports r JOIN activities a ON a.id=r.activity_id WHERE r.status='pending'"):
            result.append({'kind': 'report', 'id': row['id'], 'title': '活动举报处理：' + row['title'], 'deadline': None, 'activity_id': row['activity_id'], 'club_id': row['club_id']})
    return ok(sorted(result, key=lambda item: (item['deadline'] is None, item['deadline'] or '', item['kind'], item['id'])))


@extensions.get('/venues')
def venues():
    return ok([dict(row) for row in get_db().execute('SELECT id,name,description FROM venues ORDER BY id')])


def venue_application_json(row):
    result = dict(row)
    activity = get_row('activities', row['activity_id'])
    result['activity_title'] = activity['title']
    result['club_id'] = activity['club_id']
    result['venue_name'] = get_row('venues', row['venue_id'])['name']
    return result


@extensions.get('/venue-applications')
def venue_applications():
    require_any_leader()
    if g.user['role'] == 'staff':
        rows = get_db().execute('SELECT * FROM venue_applications ORDER BY id DESC')
    else:
        rows = get_db().execute("SELECT v.* FROM venue_applications v JOIN activities a ON a.id=v.activity_id WHERE EXISTS(SELECT 1 FROM memberships m WHERE m.club_id=a.club_id AND m.user_id=? AND m.role='leader' AND m.active=1) ORDER BY v.id DESC", (g.user['id'],))
    return ok([venue_application_json(row) for row in rows])


def validate_venue_interval(activity, start, end):
    if activity['status'] not in VENUE_ACTIVITY_STATUSES:
        fail('只有已提交且尚未结束或取消的活动可以申请或获批场地。', 409, 'invalid_state')
    if not activity['start_time'] <= start < end <= activity['end_time']:
        fail('场地使用时段必须是活动起止时间内的有效区间。')
    if start < iso():
        fail('场地使用开始时间不能早于当前时间。')


@extensions.post('/activities/<int:activity_id>/venue-applications')
def create_venue_application(activity_id):
    require_user()
    data = body()
    venue_id = integer(data.get('venue_id'), '场地', maximum=2147483647)
    start = timestamp(data.get('start_time'), '场地使用开始时间')
    end = timestamp(data.get('end_time'), '场地使用结束时间')
    with transaction() as connection:
        refresh_lifecycle(connection)
        activity = get_row('activities', activity_id, '活动')
        require_leader(activity['club_id'], write=True)
        get_row('venues', venue_id, '场地')
        validate_venue_interval(activity, start, end)
        if connection.execute("SELECT 1 FROM venue_applications WHERE activity_id=? AND venue_id=? AND start_time=? AND end_time=? AND status IN ('pending','approved')", (activity_id, venue_id, start, end)).fetchone():
            fail('已有相同待审或批准的场地申请。', 409, 'conflict')
        record_id = connection.execute('INSERT INTO venue_applications(activity_id,venue_id,start_time,end_time,created_by,created_at) VALUES(?,?,?,?,?,?)', (activity_id, venue_id, start, end, g.user['id'], iso())).lastrowid
        for staff in connection.execute("SELECT id FROM users WHERE role='staff'").fetchall():
            notify(staff['id'], '场地申请待审核', f'{activity["title"]}已提交场地申请。')
        audit('venue_application_created', 'venue_application', record_id)
    return ok(venue_application_json(get_row('venue_applications', record_id)), 201)


@extensions.post('/venue-applications/<int:application_id>/review')
def review_venue_application(application_id):
    user = require_staff()
    choice, reason = decision(body())
    with transaction() as connection:
        refresh_lifecycle(connection)
        row = get_row('venue_applications', application_id, '场地申请')
        activity = get_row('activities', row['activity_id'])
        if row['status'] != 'pending':
            fail('场地申请已经处理。', 409, 'invalid_state')
        if choice == 'approve':
            require_active_club(activity['club_id'])
            validate_venue_interval(activity, row['start_time'], row['end_time'])
            conflict = connection.execute("SELECT id FROM venue_applications WHERE venue_id=? AND status='approved' AND start_time<? AND end_time>? LIMIT 1", (row['venue_id'], row['end_time'], row['start_time'])).fetchone()
            if conflict:
                fail('同场地的使用时段与已批准申请重叠。', 409, 'venue_conflict')
        status = 'approved' if choice == 'approve' else 'rejected'
        connection.execute('UPDATE venue_applications SET status=?,reason=?,reviewed_by=?,reviewed_at=? WHERE id=?', (status, reason, user['id'], iso(), application_id))
        audit('venue_application_' + status, 'venue_application', application_id, {'reason': reason})
        for owner in leaders_of(activity['club_id']):
            notify(owner, '场地申请结果', f'{activity["title"]}：场地申请' + ('已通过。' if choice == 'approve' else '已驳回。') + reason)
    return ok(venue_application_json(get_row('venue_applications', application_id)))


@extensions.get('/activities/<int:activity_id>/materials')
def materials(activity_id):
    activity = get_row('activities', activity_id, '活动')
    staff_or_leader(activity['club_id'])
    return ok([dict(row) for row in get_db().execute('SELECT id,name,quantity,status FROM materials WHERE activity_id=? ORDER BY id', (activity_id,))])


@extensions.post('/activities/<int:activity_id>/materials')
def create_material(activity_id):
    require_user()
    data = body()
    name, quantity = text(data.get('name'), '物资名称', 120), integer(data.get('quantity'), '物资数量')
    with transaction() as connection:
        activity = get_row('activities', activity_id, '活动')
        require_leader(activity['club_id'], write=True)
        record_id = connection.execute('INSERT INTO materials(activity_id,name,quantity,created_at) VALUES(?,?,?,?)', (activity_id, name, quantity, iso())).lastrowid
        audit('material_requested', 'material', record_id)
    return ok(dict(get_row('materials', record_id)), 201)


@extensions.patch('/materials/<int:material_id>')
def update_material(material_id):
    require_user()
    status = body().get('status')
    if status not in ('requested', 'preparing', 'ready'):
        fail('物资状态必须为 requested、preparing 或 ready。')
    with transaction() as connection:
        row = get_row('materials', material_id, '物资记录')
        activity = get_row('activities', row['activity_id'])
        require_leader(activity['club_id'], write=True)
        if status != row['status']:
            connection.execute('UPDATE materials SET status=? WHERE id=?', (status, material_id))
            audit('material_status_changed', 'material', material_id, {'from': row['status'], 'to': status})
    return ok(dict(get_row('materials', material_id)))


@extensions.post('/activities/<int:activity_id>/feedback')
def create_feedback(activity_id):
    user = require_student()
    data = body()
    rating = integer(data.get('rating'), '评分', minimum=1, maximum=5)
    comment = text(data.get('comment', ''), '评价内容', allow_empty=True)
    with transaction() as connection:
        refresh_lifecycle(connection)
        activity = get_row('activities', activity_id, '活动')
        if activity['status'] not in ('Finished', 'Archived'):
            fail('活动结束后才可以评价。', 409, 'invalid_state')
        registration = connection.execute("SELECT 1 FROM registrations WHERE activity_id=? AND user_id=? AND status='confirmed' AND checked_in=1", (activity_id, user['id'])).fetchone()
        if registration is None:
            fail('只有本人已正式报名并签到的活动可以评价。', 403, 'forbidden')
        if connection.execute('SELECT 1 FROM feedback WHERE activity_id=? AND user_id=?', (activity_id, user['id'])).fetchone():
            fail('已经评价过该活动。', 409, 'conflict')
        record_id = connection.execute('INSERT INTO feedback(activity_id,user_id,rating,comment,created_at) VALUES(?,?,?,?,?)', (activity_id, user['id'], rating, comment, iso())).lastrowid
        audit('feedback_created', 'feedback', record_id)
        for owner in leaders_of(activity['club_id']):
            notify(owner, '收到活动评价', f'{activity["title"]}收到一条新的参与评价。')
    return ok({'id': record_id, 'activity_id': activity_id, 'rating': rating, 'comment': comment}, 201)


def statistics_data(club_id):
    club = get_row('clubs', club_id, '社团')
    staff_or_leader(club_id)
    rows = get_db().execute("SELECT a.id,a.title,a.status,(SELECT COUNT(*) FROM registrations r WHERE r.activity_id=a.id AND r.status='confirmed') registration_count,(SELECT COUNT(*) FROM registrations r WHERE r.activity_id=a.id AND r.status='confirmed' AND r.checked_in=1) check_in_count,(SELECT COUNT(*) FROM feedback f WHERE f.activity_id=a.id) feedback_count FROM activities a WHERE a.club_id=? AND a.status IN ('Finished','Archived') ORDER BY a.start_time,a.id", (club_id,))
    return {'club_id': club_id, 'club_name': club['name'], 'activities': [dict(row) for row in rows]}


@extensions.get('/clubs/<int:club_id>/statistics')
def statistics(club_id):
    return ok(statistics_data(club_id))


def spreadsheet_text(value):
    # Quoting CSV delimiters alone does not prevent formula execution in a spreadsheet.
    if value.lstrip(' \t\r\n').startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
        return "'" + value
    return value


@extensions.get('/clubs/<int:club_id>/statistics.csv')
def statistics_csv(club_id):
    data = statistics_data(club_id)
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['活动ID', '活动标题', '活动状态', '正式报名数', '签到数', '评价数'])
    for row in data['activities']:
        writer.writerow([row['id'], spreadsheet_text(row['title']), row['status'], row['registration_count'], row['check_in_count'], row['feedback_count']])
    response = Response('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
    response.headers['Content-Disposition'] = f'attachment; filename="club-{club_id}-statistics.csv"'
    return response


@extensions.get('/recommendations')
def recommendations():
    require_student()
    selected = text(request.args.get('themes', ''), '偏好主题', 1000, allow_empty=True)
    themes = {text(value, '偏好主题', 120) for value in selected.split(',') if value.strip()}
    if len(themes) > 20:
        fail('最多选择 20 个偏好主题。')
    rows = get_db().execute('SELECT * FROM activities WHERE status IN (' + ','.join('?' for _ in PUBLIC_STATUSES) + ')', PUBLIC_STATUSES).fetchall()
    rows = sorted(rows, key=lambda row: (row['theme'] not in themes, row['start_time'], row['id']))
    results = []
    for row in rows:
        value = activity_json(row)
        value['recommendation_reason'] = f'匹配偏好主题“{row["theme"]}”；按活动开始时间排序。' if row['theme'] in themes else '按活动开始时间排序。'
        results.append(value)
    return ok(results)


@extensions.post('/activities/<int:activity_id>/reports')
def create_report(activity_id):
    user = require_student()
    reason = text(body().get('reason'), '举报原因')
    with transaction() as connection:
        activity = get_row('activities', activity_id, '活动')
        if activity['status'] not in PUBLIC_STATUSES:
            fail('活动不存在或尚未公开。', 404, 'not_found')
        if connection.execute('SELECT 1 FROM reports WHERE activity_id=? AND user_id=? AND reason=?', (activity_id, user['id'], reason)).fetchone():
            fail('已经提交过相同原因的举报。', 409, 'conflict')
        record_id = connection.execute('INSERT INTO reports(activity_id,user_id,reason,created_at) VALUES(?,?,?,?)', (activity_id, user['id'], reason, iso())).lastrowid
        audit('report_created', 'report', record_id)
        for staff in connection.execute("SELECT id FROM users WHERE role='staff'").fetchall():
            notify(staff['id'], '活动举报待处理', f'{activity["title"]}收到一条活动举报。')
    return ok(dict(get_row('reports', record_id)), 201)


@extensions.get('/reports')
def reports():
    user = require_user()
    where, arguments = ('1=1', ()) if user['role'] == 'staff' else ('r.user_id=?', (user['id'],))
    return ok([dict(row) for row in get_db().execute('SELECT r.id,r.activity_id,a.title activity_title,r.reason,r.status,r.resolution FROM reports r JOIN activities a ON a.id=r.activity_id WHERE ' + where + ' ORDER BY r.id DESC', arguments)])


@extensions.post('/reports/<int:report_id>/resolve')
def resolve_report(report_id):
    user = require_staff()
    resolution = text(body().get('resolution'), '处理结果')
    with transaction() as connection:
        row = get_row('reports', report_id, '举报')
        if row['status'] != 'pending':
            fail('举报已经处理。', 409, 'invalid_state')
        connection.execute("UPDATE reports SET status='resolved',resolution=?,resolved_by=?,resolved_at=? WHERE id=?", (resolution, user['id'], iso(), report_id))
        audit('report_resolved', 'report', report_id)
        activity = get_row('activities', row['activity_id'])
        notify(row['user_id'], '活动举报处理结果', f'{activity["title"]}：{resolution}')
    return ok(dict(get_row('reports', report_id)))
