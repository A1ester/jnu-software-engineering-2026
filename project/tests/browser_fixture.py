"""Build a new independent database for browser acceptance tests."""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from campus_clubs import create_app
from campus_clubs.db import get_db, iso, seed_demo, transaction


def build_fixture(path):
    if path.exists():
        raise ValueError('浏览器验证必须使用不存在的新数据库，不能覆盖已有数据。')
    instant = datetime.now(timezone.utc)
    app = create_app({'DATABASE': str(path.resolve()), 'NOW': lambda: instant})
    with app.app_context():
        seed_demo()
        with transaction() as connection:
            activity_id = connection.execute(
                '''INSERT INTO activities(club_id,title,theme,description,location,capacity,
                registration_deadline,start_time,end_time,status,created_by,created_at)
                VALUES(1,?,?,?,?,?,?,?,?,?,?,?)''',
                ('摄影复盘分享', '摄影', '用于验证已结束活动的评价与统计。', '学生交流中心', 12,
                 iso(instant - timedelta(hours=4)), iso(instant - timedelta(hours=3)),
                 iso(instant - timedelta(hours=1)), 'Finished', 2, iso()),
            ).lastrowid
            connection.execute(
                '''INSERT INTO registrations(activity_id,user_id,status,checked_in,
                created_at,checked_in_at) VALUES(?,3,'confirmed',1,?,?)''',
                (activity_id, iso(instant - timedelta(hours=5)), iso(instant - timedelta(hours=2))),
            )
        assert get_db().execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    print('独立浏览器验证数据库已生成：', path.resolve())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='创建独立浏览器测试数据')
    parser.add_argument('database', type=Path)
    args = parser.parse_args()
    build_fixture(args.database)
