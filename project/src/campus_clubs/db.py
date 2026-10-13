"""SQLite connection, transactional business writes, and explicit demo initialization."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import current_app, g
from werkzeug.security import generate_password_hash


def now():
    clock = current_app.config.get('NOW')
    value = clock() if clock else datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('NOW must return a timezone-aware datetime')
    return value.astimezone(timezone.utc)


def iso(value=None):
    return (value or now()).astimezone(timezone.utc).isoformat(timespec='microseconds')


def get_db():
    if 'db' not in g:
        connection = sqlite3.connect(current_app.config['DATABASE'], timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=15000')
        g.db = connection
    return g.db


def close_db(error=None):
    connection = g.pop('db', None)
    if connection is not None:
        connection.close()


def init_db():
    get_db().executescript(Path(__file__).with_name('schema.sql').read_text(encoding='utf-8'))


@contextmanager
def transaction():
    connection = get_db()
    connection.execute('BEGIN IMMEDIATE')
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def notify(user_id, title, message):
    get_db().execute('INSERT INTO notifications(user_id,title,message,created_at) VALUES(?,?,?,?)',
                     (user_id, title, message, iso()))


def audit(action, entity_type, entity_id, details=None, actor_id=None):
    if actor_id is None and getattr(g, 'user', None) is not None:
        actor_id = g.user['id']
    get_db().execute('INSERT INTO audit_events(actor_id,action,entity_type,entity_id,details,created_at) VALUES(?,?,?,?,?,?)',
                     (actor_id, action, entity_type, entity_id, json.dumps(details or {}, ensure_ascii=False), iso()))


def runtime_log(event_type, result, message, entity_type=None, entity_id=None):
    get_db().execute('INSERT INTO runtime_logs(event_type,result,message,entity_type,entity_id,created_at) VALUES(?,?,?,?,?,?)',
                     (event_type, result, message, entity_type, entity_id, iso()))


def seed_demo():
    """Populate an empty database only. All times are relative to the injected clock."""
    connection = get_db()
    tables = ('users', 'clubs', 'memberships', 'applications', 'club_registrations', 'activities',
              'registrations', 'tasks', 'notifications', 'audit_events', 'runtime_logs', 'sessions',
              'venues', 'venue_applications', 'materials', 'feedback', 'reports')
    with transaction():
        if any(connection.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone() for table in tables):
            raise ValueError('数据库已有记录，拒绝覆盖；请为演示初始化指定独立的空数据库。')
        names = [('student', '演示学生', 'student'), ('leader', '摄影社演示负责人', 'student'),
                 ('member', '摄影社演示成员', 'student'), ('other_leader', '读书社演示负责人', 'student'),
                 ('staff', '管理中心演示工作人员', 'staff')]
        for username, display_name, role in names:
            connection.execute('INSERT INTO users(username,display_name,password_hash,role) VALUES(?,?,?,?)',
                               (username, display_name, generate_password_hash('Demo12345!', method='scrypt'), role))
        connection.executemany('INSERT INTO clubs(name,description,created_at) VALUES(?,?,?)',
                               [('校园摄影社', '用摄影记录校园，开展交流与实践。', iso()),
                                ('读书社', '分享阅读体验，开展主题读书活动。', iso())])
        connection.executemany('INSERT INTO venues(name,description) VALUES(?,?)',
                               [('学生活动中心', '课程演示场地，可开展社团交流和实践活动。'),
                                ('图书馆交流室', '课程演示场地，适合小型阅读与讨论活动。')])
        connection.executemany('INSERT INTO memberships(club_id,user_id,role,created_at) VALUES(?,?,?,?)',
                               [(1, 2, 'leader', iso()), (1, 3, 'member', iso()), (2, 4, 'leader', iso())])
        instant = now()
        activities = [('校园摄影漫步', '摄影', '一起记录校园秋日风景。', '图书馆门口', 10,
                       instant + timedelta(days=2), instant + timedelta(days=3), instant + timedelta(days=3, hours=2), 1, 'RegistrationOpen'),
                      ('摄影交流实践', '摄影', '进行中的摄影实践，用于签到演示。', '学生活动中心', 10,
                       instant - timedelta(hours=2), instant - timedelta(minutes=30), instant + timedelta(hours=2), 0, 'InProgress'),
                      ('秋日主题展筹备', '展览', '提交审核的校园摄影展。', '活动中心展厅', 30,
                       instant + timedelta(days=6), instant + timedelta(days=7), instant + timedelta(days=7, hours=3), 0, 'Submitted')]
        for title, theme, description, location, capacity, deadline, start, end, waitlist, status in activities:
            connection.execute('INSERT INTO activities(club_id,title,theme,description,location,capacity,registration_deadline,start_time,end_time,waitlist_enabled,status,created_by,created_at) VALUES(1,?,?,?,?,?,?,?,?,?,?,2,?)',
                               (title, theme, description, location, capacity, iso(deadline), iso(start), iso(end), waitlist, status, iso()))
        connection.execute('INSERT INTO registrations(activity_id,user_id,status,created_at) VALUES(2,3,?,?)', ('confirmed', iso()))
        connection.execute('INSERT INTO tasks(activity_id,title,assignee_id,due_time,created_at) VALUES(1,?,3,?,?)',
                           ('准备摄影路线', iso(instant + timedelta(days=1)), iso()))
        notify(3, '任务分配', '校园摄影漫步：请准备摄影路线。')
        audit('demo_initialized', 'system', 0, {'accounts': 5}, actor_id=5)
