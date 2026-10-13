"""Revocable server-side sessions and resource-aware authorization."""
import hashlib
import secrets
from datetime import timedelta

from flask import current_app, g, request

from .db import get_db, iso, now


class APIError(Exception):
    def __init__(self, message, status=400, code='invalid_input'):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


def fail(message, status=400, code='invalid_input'):
    raise APIError(message, status, code)


def token_digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def load_session():
    g.user, g.auth_session = None, None
    token = request.cookies.get(current_app.config['SESSION_COOKIE_NAME'])
    if token and len(token) <= 200:
        row = get_db().execute('SELECT * FROM sessions WHERE token_hash=? AND expires_at>?', (token_digest(token), iso())).fetchone()
        if row:
            g.auth_session = row
            if row['user_id'] is not None:
                g.user = get_db().execute('SELECT id,username,display_name,role FROM users WHERE id=?', (row['user_id'],)).fetchone()


def create_session(user_id=None):
    if getattr(g, 'auth_session', None):
        get_db().execute('DELETE FROM sessions WHERE token_hash=?', (g.auth_session['token_hash'],))
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    get_db().execute('DELETE FROM sessions WHERE expires_at<=?', (iso(),))
    get_db().execute('INSERT INTO sessions(token_hash,user_id,csrf_token,created_at,expires_at) VALUES(?,?,?,?,?)',
                     (token_digest(token), user_id, csrf, iso(), iso(now() + timedelta(seconds=current_app.config['SESSION_TTL_SECONDS']))))
    g.cookie_token = token
    g.auth_session = get_db().execute('SELECT * FROM sessions WHERE token_hash=?', (token_digest(token),)).fetchone()


def require_csrf():
    candidate = request.headers.get('X-CSRF-Token', '')
    if not g.auth_session or not candidate or not secrets.compare_digest(candidate, g.auth_session['csrf_token']):
        fail('会话已失效或请求校验失败，请刷新页面后重试。', 403, 'csrf_invalid')


def require_user():
    if g.user is None:
        fail('请先登录。', 401, 'authentication_required')
    return g.user


def require_student():
    user = require_user()
    if user['role'] != 'student':
        fail('该操作仅面向学生用户。', 403, 'forbidden')
    return user


def require_staff():
    user = require_user()
    if user['role'] != 'staff':
        fail('需要学校社团管理中心工作人员权限。', 403, 'forbidden')
    return user


def membership(club_id, user_id=None):
    user_id = user_id if user_id is not None else (g.user['id'] if g.user else None)
    return get_db().execute('SELECT * FROM memberships WHERE club_id=? AND user_id=? AND active=1', (club_id, user_id)).fetchone()


def leader(club_id):
    relation = membership(club_id)
    return relation is not None and relation['role'] == 'leader'


def require_leader(club_id, write=False):
    require_user()
    if not leader(club_id):
        fail('只能管理本人负责的社团。', 403, 'forbidden')
    if write:
        require_active_club(club_id)


def require_active_club(club_id):
    row = get_db().execute('SELECT status FROM clubs WHERE id=?', (club_id,)).fetchone()
    if row is None:
        fail('社团不存在。', 404, 'not_found')
    if row['status'] != 'active':
        fail('社团已停用，暂不能开展社团业务。', 409, 'invalid_state')


def user_json():
    if g.user is None:
        return None
    result = dict(g.user)
    result['memberships'] = [dict(row) for row in get_db().execute(
        'SELECT m.club_id,c.name club_name,m.role,m.active FROM memberships m JOIN clubs c ON c.id=m.club_id WHERE m.user_id=? ORDER BY c.id', (g.user['id'],))]
    for relation in result['memberships']:
        relation['active'] = bool(relation['active'])
    return result
