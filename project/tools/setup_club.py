"""Import a confirmed club profile and set account passwords interactively on this computer."""
import argparse
import getpass
import json
from pathlib import Path
import sqlite3
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'src'))

from campus_clubs import create_app
from campus_clubs.club_setup import import_club_profile, set_local_password, validate_profile
from campus_clubs.db import get_db


def main():
    parser = argparse.ArgumentParser(description='本地社团资料与负责人账号设置')
    parser.add_argument('--database', type=Path, default=PROJECT / 'instance' / 'campus-clubs.sqlite3')
    commands = parser.add_subparsers(dest='command', required=True)
    importer = commands.add_parser('import', help='录入经确认的社团资料；不生成学校审核记录')
    importer.add_argument('profile', type=Path)
    password_command = commands.add_parser('password', help='在本机交互设置账号密码，不接收命令行密码')
    password_command.add_argument('username')
    args = parser.parse_args()
    try:
        if not args.database.is_file():
            raise ValueError('请先初始化或指定已有项目数据库。')
        if args.command == 'import':
            if args.profile.stat().st_size > 65536:
                raise ValueError('社团资料文件过大。')
            profile = validate_profile(json.loads(args.profile.read_text(encoding='utf-8-sig')))
        elif not sys.stdin.isatty():
            raise ValueError('请在本机 PowerShell 窗口中交互设置密码，不能通过重定向输入。')
        app = create_app({'DATABASE': str(args.database.resolve())})
        with app.app_context():
            if args.command == 'import':
                result = import_club_profile(profile)
                print('已录入社团：', profile['name'])
                print('负责人账号：', result['leader_username'])
                if result['password_pending']:
                    print('该账号尚不能登录，请在本机运行 password 子命令设置密码。')
            else:
                if get_db().execute('SELECT 1 FROM users WHERE username=?', (args.username,)).fetchone() is None:
                    raise ValueError('账号不存在。')
                password = getpass.getpass('设置密码（12～128 个字符，输入不回显）：')
                confirmation = getpass.getpass('再次输入密码：')
                if password != confirmation:
                    raise ValueError('两次密码不一致，未更改账号。')
                set_local_password(args.username, password)
                print('密码已设置，可使用该账号登录。')
        return 0
    except (ValueError, OSError, sqlite3.Error, EOFError) as error:
        print('设置失败：' + str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\n已取消，未设置密码。', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
