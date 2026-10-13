"""Confirmed-profile import, account setup and ownership checks on isolated databases."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from campus_clubs import create_app
from campus_clubs.club_setup import import_club_profile, set_local_password
from campus_clubs.db import get_db, seed_demo
from werkzeug.security import check_password_hash


class ClubSetupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'DATABASE': str(Path(self.directory.name) / 'setup.sqlite3')})
        with self.app.app_context():
            seed_demo()
        self.profile = {
            'name': '测试科技社', 'school': '测试学校', 'campus': '测试校区',
            'description': '用于独立验证的社团简介。',
            'leader_username': 'president_test', 'leader_display_name': '测试负责人',
        }

    def tearDown(self):
        self.directory.cleanup()

    def snapshot(self, table):
        return [tuple(row) for row in get_db().execute(f'SELECT * FROM {table} ORDER BY id')]

    def test_import_preserves_existing_records_and_creates_no_activities_or_approvals(self):
        with self.app.app_context():
            original = {table: self.snapshot(table) for table in ('users', 'clubs', 'memberships', 'activities')}
            result = import_club_profile(self.profile)
            for table, rows in original.items():
                self.assertEqual(self.snapshot(table)[:len(rows)], rows)
            club = get_db().execute('SELECT * FROM clubs WHERE id=?', (result['club_id'],)).fetchone()
            self.assertIn('测试校区', club['description'])
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM activities WHERE club_id=?', (result['club_id'],)).fetchone()[0], 0)
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM club_registrations').fetchone()[0], 0)
            self.assertTrue(result['password_pending'])

    def test_repeat_import_is_idempotent_and_has_no_shared_default_password(self):
        with self.app.app_context():
            first = import_club_profile(self.profile)
            second = import_club_profile(self.profile)
            self.assertEqual(first, second)
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM clubs').fetchone()[0], 3)
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM audit_events WHERE action='club_profile_imported'").fetchone()[0], 1)
            password_hash = get_db().execute('SELECT password_hash FROM users WHERE username=?', ('president_test',)).fetchone()[0]
            for password in ('Demo12345!', '', 'any-password'):
                self.assertFalse(check_password_hash(password_hash, password))

    def test_conflicting_leader_rolls_back_without_creating_a_new_user(self):
        with self.app.app_context():
            before = {table: self.snapshot(table) for table in ('users', 'clubs', 'memberships', 'audit_events')}
            with self.assertRaises(ValueError):
                import_club_profile(dict(self.profile, name='校园摄影社'))
            for table, rows in before.items():
                self.assertEqual(self.snapshot(table), rows)

    def test_password_setup_and_role_are_limited_to_the_imported_club(self):
        with self.app.app_context():
            result = import_club_profile(self.profile)
            set_local_password('president_test', 'TestPasswordOnly2026!')
            user = get_db().execute('SELECT * FROM users WHERE username=?', ('president_test',)).fetchone()
            self.assertNotEqual(user['password_hash'], 'TestPasswordOnly2026!')
            self.assertTrue(user['password_hash'].startswith('scrypt:'))
            get_db().execute("INSERT INTO sessions(token_hash,user_id,csrf_token,created_at,expires_at) VALUES('old-test-session',?,'csrf','2000','2999')", (user['id'],))
            set_local_password('president_test', 'ReplacementTest2026!')
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM sessions WHERE token_hash='old-test-session'").fetchone()[0], 0)
        client = self.app.test_client()
        csrf = client.get('/api/session').get_json()['data']['csrf_token']
        login = client.post('/api/login', json={'username': 'president_test', 'password': 'ReplacementTest2026!'}, headers={'X-CSRF-Token': csrf})
        self.assertEqual(login.status_code, 200)
        user = login.get_json()['data']['user']
        self.assertEqual(user['role'], 'student')
        self.assertEqual([(membership['club_id'], membership['role']) for membership in user['memberships']], [(result['club_id'], 'leader')])
        self.assertEqual(client.get('/api/clubs/1/members').status_code, 403)

    def test_invalid_profile_and_password_do_not_change_existing_data(self):
        with self.app.app_context():
            before = self.snapshot('users')
            with self.assertRaises(ValueError):
                import_club_profile(dict(self.profile, password='must-not-be-in-profile'))
            with self.assertRaises(ValueError):
                import_club_profile(dict(self.profile, leader_username='staff'))
            with self.assertRaises(ValueError):
                set_local_password('student', 'short')
            self.assertEqual(self.snapshot('users'), before)


if __name__ == '__main__':
    unittest.main()
