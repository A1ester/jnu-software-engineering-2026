"""Initialize a new isolated test runtime; never copy a working database or its sessions."""
import argparse
import json
import os
from pathlib import Path
import shlex
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from campus_clubs import create_app
from campus_clubs.club_setup import import_club_profile, validate_profile
from campus_clubs.db import audit, get_db, seed_demo, transaction


def main():
    parser = argparse.ArgumentParser(description='初始化独立云端测试运行目录')
    parser.add_argument('bootstrap', type=Path)
    parser.add_argument('runtime', type=Path)
    args = parser.parse_args()
    payload = json.loads(args.bootstrap.read_text(encoding='utf-8'))
    profile = validate_profile(payload['profile'])
    digest = payload['gate_password_sha256']
    if len(digest) != 64 or any(character not in '0123456789abcdef' for character in digest):
        parser.error('测试口令摘要无效。')
    if not payload['leader_password_hash'].startswith('scrypt:'):
        parser.error('负责人测试密码摘要无效。')
    if payload['gate_username'] != 'club-test':
        parser.error('测试访问账号无效。')
    os.umask(0o077)
    runtime = args.runtime.resolve()
    runtime.mkdir(parents=True, exist_ok=False, mode=0o700)
    database = runtime / 'cloud-test.sqlite3'
    app = create_app({'DATABASE': str(database)})
    with app.app_context():
        seed_demo()
        result = import_club_profile(profile)
        with transaction():
            user = get_db().execute('SELECT id FROM users WHERE username=?', (result['leader_username'],)).fetchone()
            get_db().execute('UPDATE users SET password_hash=? WHERE id=?', (payload['leader_password_hash'], user['id']))
            audit('account_password_set', 'user', user['id'])
        assert get_db().execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    settings = {'CLUB_DATABASE': str(database), 'CLUB_TEST_USERNAME': payload['gate_username'],
                'CLUB_TEST_PASSWORD_SHA256': digest, 'CLUB_PORT': '6006'}
    with (runtime / 'service.env').open('x', encoding='utf-8', newline='\n') as stream:
        for key, value in settings.items():
            stream.write(f'{key}={shlex.quote(value)}\n')
    print('独立云端测试数据已初始化。')


if __name__ == '__main__':
    main()
