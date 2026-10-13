"""Local setup for confirmed club profiles, without creating approval records."""
from .db import audit, get_db, iso, transaction
from werkzeug.security import generate_password_hash


PROFILE_FIELDS = {
    'name': 120, 'school': 120, 'campus': 120, 'description': 1600,
    'leader_username': 64, 'leader_display_name': 120,
}


def validate_profile(profile):
    if not isinstance(profile, dict) or set(profile) != set(PROFILE_FIELDS):
        raise ValueError('资料必须且只能包含社团名称、学校、校区、简介、负责人账号和显示名。')
    values = {}
    for key, limit in PROFILE_FIELDS.items():
        value = profile[key]
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
            raise ValueError(f'资料字段 {key} 为空或超过长度限制。')
        if any(ord(character) < 32 and character not in '\n\r\t' for character in value):
            raise ValueError(f'资料字段 {key} 包含无效控制字符。')
        values[key] = value.strip()
    return values


def import_club_profile(profile):
    values = validate_profile(profile)
    description = f"所属学校：{values['school']}；校区：{values['campus']}。\n\n{values['description']}"
    if len(description) > 2000:
        raise ValueError('社团介绍总长度超过 2000 字符。')
    connection = get_db()
    with transaction():
        club = connection.execute('SELECT * FROM clubs WHERE name=?', (values['name'],)).fetchone()
        user = connection.execute('SELECT * FROM users WHERE username=?', (values['leader_username'],)).fetchone()
        if user and user['role'] != 'student':
            raise ValueError('负责人必须是学生用户，不能把管理中心账号改为社团负责人。')
        if club:
            owner = connection.execute(
                "SELECT user_id FROM memberships WHERE club_id=? AND role='leader' AND active=1", (club['id'],)
            ).fetchone()
            if owner and (not user or owner['user_id'] != user['id']):
                raise ValueError('社团已有其他有效负责人，请通过正式负责人变更流程处理。')
        user_created = user is None
        changed = False
        if user_created:
            # Unusable until the owner chooses a password locally. No shared default password.
            user_id = connection.execute(
                'INSERT INTO users(username,display_name,password_hash,role) VALUES(?,?,?,?)',
                (values['leader_username'], values['leader_display_name'], '!', 'student'),
            ).lastrowid
            changed = True
        else:
            user_id = user['id']
            if user['display_name'] != values['leader_display_name']:
                connection.execute('UPDATE users SET display_name=? WHERE id=?', (values['leader_display_name'], user_id))
                changed = True
        if club is None:
            club_id = connection.execute('INSERT INTO clubs(name,description,created_at) VALUES(?,?,?)',
                                         (values['name'], description, iso())).lastrowid
            changed = True
        else:
            club_id = club['id']
            if club['description'] != description:
                connection.execute('UPDATE clubs SET description=? WHERE id=?', (description, club_id))
                changed = True
        membership = connection.execute('SELECT * FROM memberships WHERE club_id=? AND user_id=?', (club_id, user_id)).fetchone()
        if membership is None:
            connection.execute('INSERT INTO memberships(club_id,user_id,role,created_at) VALUES(?,?,?,?)',
                               (club_id, user_id, 'leader', iso()))
            changed = True
        elif membership['role'] != 'leader' or not membership['active']:
            connection.execute("UPDATE memberships SET role='leader',active=1 WHERE id=?", (membership['id'],))
            changed = True
        if changed:
            audit('club_profile_imported', 'club', club_id,
                  {'source': '社长确认的本地预览资料', 'leader_username': values['leader_username']})
        password_pending = connection.execute('SELECT password_hash FROM users WHERE id=?', (user_id,)).fetchone()[0] == '!'
    return {'club_id': club_id, 'leader_username': values['leader_username'], 'password_pending': password_pending}


def set_local_password(username, password):
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValueError('密码长度应为 12～128 个字符。')
    with transaction():
        user = get_db().execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
        if user is None:
            raise ValueError('账号不存在。')
        get_db().execute('UPDATE users SET password_hash=? WHERE id=?',
                         (generate_password_hash(password, method='scrypt'), user['id']))
        get_db().execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
        audit('account_password_set', 'user', user['id'])
