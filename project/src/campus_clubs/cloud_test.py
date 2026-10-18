"""Authenticated WSGI entry point for a temporary HTTPS deployment test."""
import base64
import binascii
import hashlib
import hmac
import os
from pathlib import Path

from . import create_app


class TestAccessGate:
    def __init__(self, application, username, password_digest):
        self.application = application
        self.username = username.encode('utf-8')
        self.password_digest = bytes.fromhex(password_digest)

    def __call__(self, environ, start_response):
        authorization = environ.get('HTTP_AUTHORIZATION', '')
        authenticated = False
        if len(authorization) <= 4096:
            scheme, _, encoded = authorization.partition(' ')
            if scheme.lower() == 'basic':
                try:
                    decoded = base64.b64decode(encoded, validate=True).decode('utf-8')
                    username, separator, password = decoded.partition(':')
                    authenticated = bool(separator) and hmac.compare_digest(username.encode('utf-8'), self.username)
                    authenticated = authenticated and hmac.compare_digest(hashlib.sha256(password.encode('utf-8')).digest(), self.password_digest)
                except (ValueError, UnicodeError, binascii.Error):
                    pass
        if authenticated:
            return self.application(environ, start_response)
        body = '测试站点需要访问账号与口令。\n'.encode('utf-8')
        start_response('401 Unauthorized', [
            ('WWW-Authenticate', 'Basic realm="Campus club test", charset="UTF-8"'),
            ('Content-Type', 'text/plain; charset=utf-8'), ('Content-Length', str(len(body))),
            ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
        ])
        return [body]


def create_cloud_test_app():
    username = os.environ.get('CLUB_TEST_USERNAME', '')
    digest = os.environ.get('CLUB_TEST_PASSWORD_SHA256', '')
    database = Path(os.environ.get('CLUB_DATABASE', ''))
    if not username or len(username) > 64 or ':' in username:
        raise RuntimeError('请配置有效的 CLUB_TEST_USERNAME。')
    if len(digest) != 64 or any(character not in '0123456789abcdefABCDEF' for character in digest):
        raise RuntimeError('请配置随机测试口令的 SHA256 摘要，不接受空口令。')
    if not database.is_absolute() or not database.is_file():
        raise RuntimeError('CLUB_DATABASE 必须指向已初始化的独立测试数据库。')
    app = create_app({'DATABASE': str(database), 'SESSION_COOKIE_SECURE': True,
                      'SESSION_TTL_SECONDS': 7200, 'CLOUD_TEST_MODE': True})
    app.wsgi_app = TestAccessGate(app.wsgi_app, username, digest)

    @app.after_request
    def mark_test_environment(response):
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        response.headers['Cache-Control'] = 'no-store'
        return response

    return app
