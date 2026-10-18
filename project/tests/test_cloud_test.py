"""Temporary cloud entry point: authentication, HTTPS cookies and local-preview isolation."""
import base64
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from campus_clubs import create_app
from campus_clubs.cloud_test import create_cloud_test_app


class CloudEntryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / 'cloud.sqlite3'
        self.local = create_app({'TESTING': True, 'DATABASE': str(self.database)})
        self.environment = {
            'CLUB_DATABASE': str(self.database), 'CLUB_TEST_USERNAME': 'test-user',
            'CLUB_TEST_PASSWORD_SHA256': hashlib.sha256(b'isolated-test-passphrase').hexdigest(),
        }
        with patch.dict(os.environ, self.environment):
            self.cloud = create_cloud_test_app()
        self.client = self.cloud.test_client()
        self.authorization = 'Basic ' + base64.b64encode(b'test-user:isolated-test-passphrase').decode('ascii')

    def tearDown(self):
        self.directory.cleanup()

    def test_missing_configuration_refuses_to_start(self):
        for key in self.environment:
            with self.subTest(key=key), patch.dict(os.environ, dict(self.environment, **{key: ''})):
                with self.assertRaises(RuntimeError):
                    create_cloud_test_app()

    def test_unauthenticated_pages_api_and_static_assets_are_protected(self):
        for path in ('/', '/api/session', '/static/app.js', '/static/fonts/noto-sans-sc.woff2'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 401)
            self.assertIn('Campus club test', response.headers['WWW-Authenticate'])
            self.assertNotIn('Set-Cookie', response.headers)

    def test_malformed_and_incorrect_credentials_return_401(self):
        for value in ('Bearer token', 'Basic !!!!!', 'Basic ' + base64.b64encode(b'no-colon').decode(),
                      'Basic ' + base64.b64encode(b'test-user:incorrect').decode(),
                      'Basic ' + base64.b64encode('陌生用户:password'.encode()).decode()):
            with self.subTest(value=value):
                self.assertEqual(self.client.get('/', headers={'Authorization': value}).status_code, 401)

    def test_authenticated_pages_and_session_use_test_label_and_secure_cookie(self):
        headers = {'Authorization': self.authorization}
        response = self.client.get('/', headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn('云端测试站点', response.get_data(as_text=True))
        self.assertEqual(response.headers['X-Robots-Tag'], 'noindex, nofollow')
        session = self.client.get('/api/session', headers=headers)
        self.assertEqual(session.status_code, 200)
        for flag in ('Secure', 'HttpOnly', 'SameSite=Lax'):
            self.assertIn(flag, session.headers['Set-Cookie'])

    def test_local_preview_keeps_its_existing_access_behavior(self):
        response = self.local.test_client().get('/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('云端测试站点', response.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
