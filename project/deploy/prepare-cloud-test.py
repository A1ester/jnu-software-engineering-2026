"""Generate private, single-deployment credentials without printing their values."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from campus_clubs.club_setup import validate_profile
from werkzeug.security import generate_password_hash


def main():
    parser = argparse.ArgumentParser(description='生成云端测试的本机访问文件及仅含摘要的初始化文件')
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--url', required=True)
    args = parser.parse_args()
    url = urlsplit(args.url)
    if url.scheme != 'https' or not url.hostname or url.username or url.password:
        parser.error('请提供不含账号口令的 HTTPS 站点地址。')
    profile = validate_profile(json.loads(args.profile.read_text(encoding='utf-8-sig')))
    args.output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    access = {'url': args.url, 'gate_username': 'club-test', 'gate_password': secrets.token_urlsafe(24),
              'leader_username': profile['leader_username'], 'leader_password': secrets.token_urlsafe(24)}
    bootstrap = {'profile': profile, 'gate_username': access['gate_username'],
                 'gate_password_sha256': hashlib.sha256(access['gate_password'].encode()).hexdigest(),
                 'leader_password_hash': generate_password_hash(access['leader_password'], method='scrypt')}
    for name, content in (('access.json', access), ('bootstrap.json', bootstrap)):
        path = args.output_dir / name
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(content, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    print('本机访问文件：', (args.output_dir / 'access.json').resolve())
    print('远端初始化文件：', (args.output_dir / 'bootstrap.json').resolve())


if __name__ == '__main__':
    main()
