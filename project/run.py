"""Local course demo runner and explicit, non-overwriting SQLite recovery tools."""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))

from campus_clubs import create_app
from campus_clubs.db import seed_demo
from campus_clubs.service import tick

DEFAULT_DB = Path(__file__).resolve().parent / 'instance' / 'campus-clubs.sqlite3'
EXPECTED_TABLES = {'users', 'clubs', 'memberships', 'applications', 'club_registrations',
                   'activities', 'registrations', 'tasks', 'notifications', 'audit_events', 'runtime_logs', 'sessions',
                   'venues', 'venue_applications', 'materials', 'feedback', 'reports'}


def validate_database(path):
    if not path.is_file():
        raise ValueError('源数据库不存在或不是普通文件。')
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('源数据库完整性检查失败。')
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not EXPECTED_TABLES.issubset(tables):
            raise ValueError('源文件不是本项目的完整数据库。')
        if connection.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('源数据库关联完整性检查失败。')
    finally:
        connection.close()


def copy_database(source, target):
    source, target = source.resolve(), target.resolve()
    if source == target:
        raise ValueError('源数据库和目标必须是不同的独立文件。')
    validate_database(source)
    if not target.parent.is_dir():
        raise ValueError('目标目录不存在；请先创建所需目录。')
    # Exclusive creation prevents both accidental overwrite and a check/create race.
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    try:
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as origin:
            with sqlite3.connect(target) as destination:
                origin.backup(destination)
        validate_database(target)
    except BaseException:
        # Only this invocation's newly created destination can be removed.
        target.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description='校园社团活动管理系统课程演示')
    parser.add_argument('--database', default=str(DEFAULT_DB), help='运行数据库路径')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('init-demo', 'serve', 'tick', 'backup', 'restore'):
        command = commands.add_parser(name)
        command.add_argument('--database', default=argparse.SUPPRESS, help='运行数据库路径')
        if name == 'serve':
            command.add_argument('--host', default='127.0.0.1')
            command.add_argument('--port', type=int, default=5000)
        elif name == 'backup':
            command.add_argument('target', type=Path)
        elif name == 'restore':
            command.add_argument('source', type=Path)
            command.add_argument('target', type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.command == 'backup':
            copy_database(Path(arguments.database), arguments.target)
            print('备份已保存到独立目标：', arguments.target.resolve())
            return 0
        if arguments.command == 'restore':
            if arguments.target.resolve() == Path(arguments.database).resolve():
                raise ValueError('恢复目标必须独立于当前运行数据库。')
            copy_database(arguments.source, arguments.target)
            print('恢复完成；原运行数据库未被覆盖：', arguments.target.resolve())
            return 0
        app = create_app({'DATABASE': str(Path(arguments.database).resolve())})
        if arguments.command == 'serve':
            if not 1 <= arguments.port <= 65535:
                raise ValueError('端口必须是 1 到 65535 之间的整数。')
            print('课程本地演示服务器；请勿将演示账号直接用于公开部署。')
            app.run(host=arguments.host, port=arguments.port, threaded=True, debug=False)
        else:
            with app.app_context():
                if arguments.command == 'init-demo':
                    seed_demo()
                    print('演示初始化完成；演示口令 Demo12345!（仅用于本地课程演示）。')
                elif arguments.command == 'tick':
                    print('活动生命周期变更数量：', tick())
        return 0
    except (ValueError, sqlite3.Error, OSError) as error:
        print('操作失败：' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
