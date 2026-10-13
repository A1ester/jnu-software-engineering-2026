"""Application factory for the campus club course project."""
import logging
import sqlite3
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from .db import close_db, init_db, runtime_log, transaction
from .extensions import extensions
from .routes import api
from .security import APIError, load_session, require_csrf
from .service import tick


def create_app(config=None):
    project = Path(__file__).resolve().parents[2]
    app = Flask(__name__, instance_path=str(project / 'instance'))
    app.config.from_mapping(
        DATABASE=str(project / 'instance' / 'campus-clubs.sqlite3'), SECRET_KEY=None,
        SESSION_COOKIE_NAME='campus_session', SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=False, SESSION_COOKIE_SAMESITE='Lax', SESSION_TTL_SECONDS=28800,
        MAX_CONTENT_LENGTH=65536, NOW=None,
    )
    if config:
        app.config.update(config)
    database = str(app.config['DATABASE'])
    if database != ':memory:':
        Path(database).resolve().parent.mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(close_db)
    app.register_blueprint(api)
    app.register_blueprint(extensions)
    with app.app_context():
        init_db()

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.before_request
    def prepare_request():
        if request.path.startswith('/api/'):
            load_session()
            if request.method in ('POST', 'PATCH', 'PUT', 'DELETE'):
                require_csrf()
            tick()

    @app.after_request
    def finish_request(response):
        if getattr(g, 'cookie_token', None):
            response.set_cookie(app.config['SESSION_COOKIE_NAME'], g.cookie_token,
                                max_age=app.config['SESSION_TTL_SECONDS'], httponly=True,
                                secure=app.config['SESSION_COOKIE_SECURE'], samesite='Lax', path='/')
        if getattr(g, 'clear_cookie', False):
            response.delete_cookie(app.config['SESSION_COOKIE_NAME'], path='/')
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; object-src 'none'"
        return response

    def record_error(event_type, result, message):
        try:
            with transaction():
                runtime_log(event_type, result, message)
        except Exception:
            # Database failure cannot be logged to the same unavailable database.
            logging.getLogger(__name__).error('无法写入运行日志：%s', event_type)

    @app.errorhandler(APIError)
    def api_error(error):
        if error.code == 'invalid_credentials':
            record_error('login_failed', 'denied', '登录凭据验证失败。')
        elif error.status in (401, 403):
            record_error('unauthorized', 'denied', '访问被拒绝：' + error.code)
        return jsonify(error={'code': error.code, 'message': error.message}), error.status

    @app.errorhandler(sqlite3.IntegrityError)
    def integrity_error(error):
        return jsonify(error={'code': 'conflict', 'message': '记录重复或业务约束冲突，请刷新后重试。'}), 409

    @app.errorhandler(Exception)
    def unexpected_error(error):
        if isinstance(error, HTTPException):
            messages = {404: '请求的页面或接口不存在。', 405: '请求方法不允许。', 413: '请求内容过大。'}
            return jsonify(error={'code': 'http_error', 'message': messages.get(error.code, '请求无效。')}), error.code
        record_error('system_error', 'failed', '请求处理失败，业务事务已回滚。')
        # Do not persist exception strings, request bodies, cookies, or passwords.
        logging.getLogger(__name__).error('请求处理失败：%s', type(error).__name__)
        return jsonify(error={'code': 'system_error', 'message': '系统暂时无法处理请求，请稍后重试。'}), 500

    return app
