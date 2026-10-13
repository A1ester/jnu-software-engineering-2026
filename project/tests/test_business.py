"""Business acceptance tests against isolated, real SQLite databases.

Run from the repository root: python -m unittest discover -s project/tests -v
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from campus_clubs import create_app
from campus_clubs.db import get_db, seed_demo


class BusinessTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.now = datetime(2030, 6, 1, 12, tzinfo=timezone.utc)
        self.app = create_app({
            "TESTING": True,
            "DATABASE": str(Path(self.directory.name) / "test.sqlite3"),
            "SECRET_KEY": "isolated-test-secret-not-for-deployment",
            "NOW": lambda: self.now,
            "SESSION_TTL_SECONDS": 3600,
        })
        with self.app.app_context():
            seed_demo()
        self.clients = {}

    def tearDown(self):
        self.directory.cleanup()

    def data(self, response, status=200):
        self.assertEqual(response.status_code, status, response.get_data(as_text=True))
        value = response.get_json()
        self.assertIsInstance(value, dict)
        self.assertIn("data", value)
        return value["data"]

    def error(self, response, status):
        self.assertEqual(response.status_code, status, response.get_data(as_text=True))
        value = response.get_json()
        self.assertIn("error", value)
        self.assertTrue(value["error"]["code"])
        self.assertTrue(value["error"]["message"])

    def login(self, username, password="Demo12345!", remember=True):
        client = self.app.test_client()
        session = self.data(client.get("/api/session"))
        response = client.post("/api/login", json={"username": username, "password": password},
                               headers={"X-CSRF-Token": session["csrf_token"]})
        user_session = self.data(response)
        self.assertEqual(user_session["user"]["username"], username)
        if remember:
            self.clients[username] = (client, user_session["csrf_token"])
        return client, user_session["csrf_token"]

    def client(self, username):
        if username not in self.clients:
            self.login(username)
        return self.clients[username][0]

    def mutate(self, username, method, path, body=None):
        client = self.client(username)
        token = self.clients[username][1]
        return client.open(path, method=method, json={} if body is None else body,
                           headers={"X-CSRF-Token": token})

    def post(self, username, path, body=None):
        return self.mutate(username, "POST", path, body)

    def patch(self, username, path, body):
        return self.mutate(username, "PATCH", path, body)

    def activity_body(self, **updates):
        body = {
            "club_id": 1,
            "title": "测试校园摄影活动",
            "theme": "摄影",
            "description": "校园建筑观察与摄影交流。",
            "location": "教学楼广场",
            "capacity": 3,
            "registration_deadline": (self.now + timedelta(hours=2)).isoformat(),
            "start_time": (self.now + timedelta(hours=3)).isoformat(),
            "end_time": (self.now + timedelta(hours=4)).isoformat(),
            "waitlist_enabled": True,
        }
        body.update(updates)
        return body

    def create_activity(self, username="leader", **updates):
        return self.data(self.post(username, "/api/activities", self.activity_body(**updates)), 201)

    def transition(self, username, activity_id, action, **updates):
        return self.post(username, f"/api/activities/{activity_id}/transition", {"action": action, **updates})

    def open_activity(self, **updates):
        activity = self.create_activity(**updates)
        activity_id = activity["id"]
        for username, action, expected in [
            ("leader", "submit", "Submitted"),
            ("staff", "approve", "Approved"),
            ("leader", "publish", "Published"),
            ("leader", "open_registration", "RegistrationOpen"),
        ]:
            value = self.data(self.transition(username, activity_id, action))
            self.assertEqual(value["status"], expected)
        return activity_id

    def register(self, username, activity_id):
        return self.post(username, f"/api/activities/{activity_id}/registrations")

    def application(self, username="student", club_id=1):
        return self.data(self.post(username, f"/api/clubs/{club_id}/applications",
                                   {"message": "希望参与社团活动。"}), 201)

    def advance(self, instant):
        self.now = instant
        self.clients.clear()


class SessionAndPrivacyTests(BusinessTestCase):
    def test_login_rejects_bad_credentials_without_opening_session(self):
        for username, password in [("student", "incorrect"), ("unknown", "Demo12345!")]:
            with self.subTest(username=username):
                client = self.app.test_client()
                token = self.data(client.get("/api/session"))["csrf_token"]
                self.error(client.post("/api/login", json={"username": username, "password": password},
                                       headers={"X-CSRF-Token": token}), 401)
                self.assertIsNone(self.data(client.get("/api/session"))["user"])
                self.error(client.get("/api/my/applications"), 401)

    def test_session_and_public_clubs_do_not_expose_credentials_or_private_roster(self):
        user = self.data(self.client("student").get("/api/session"))["user"]
        self.assertEqual(user["role"], "student")
        for value in [user, self.data(self.app.test_client().get("/api/clubs")),
                      self.data(self.app.test_client().get("/api/clubs/1"))]:
            text = str(value).lower()
            self.assertNotIn("password", text)
            self.assertNotIn("secret_key", text)
            self.assertNotIn("demo12345", text)
        club = self.data(self.app.test_client().get("/api/clubs/1"))
        self.assertNotIn("members", club)
        self.error(self.client("student").get("/api/clubs/1/members"), 403)

    def test_missing_and_foreign_csrf_tokens_are_rejected_including_login(self):
        guest = self.app.test_client()
        self.error(guest.post("/api/login", json={"username": "student", "password": "Demo12345!"}), 403)
        client = self.client("student")
        self.error(client.post("/api/clubs/1/applications", json={"message": "申请"}), 403)
        foreign = self.data(self.app.test_client().get("/api/session"))["csrf_token"]
        self.error(client.post("/api/clubs/1/applications", json={"message": "申请"},
                               headers={"X-CSRF-Token": foreign}), 403)
        self.assertEqual(self.data(client.get("/api/my/applications")), [])

    def test_logout_revokes_authenticated_access(self):
        client = self.client("student")
        cookie_name = self.app.config["SESSION_COOKIE_NAME"]
        old_cookie = client.get_cookie(cookie_name).value
        self.data(self.post("student", "/api/logout"))
        self.assertIsNone(self.data(client.get("/api/session"))["user"])
        self.error(client.get("/api/my/registrations"), 401)
        replay = self.app.test_client()
        replay.set_cookie(cookie_name, old_cookie)
        self.error(replay.get("/api/my/registrations"), 401)

    def test_expired_session_is_rejected_at_expiry(self):
        client = self.client("student")
        self.now += timedelta(seconds=3600)
        self.error(client.get("/api/my/applications"), 401)
        self.assertIsNone(self.data(client.get("/api/session"))["user"])

    def test_anonymous_users_cannot_read_internal_lists(self):
        client = self.app.test_client()
        for path in ["/api/my/activities", "/api/my/clubs", "/api/tasks", "/api/notifications",
                     "/api/audit", "/api/logs", "/api/club-registrations"]:
            with self.subTest(path=path):
                self.error(client.get(path), 401)


class ClubMembershipTests(BusinessTestCase):
    def test_pending_application_is_unique_and_acceptance_creates_membership(self):
        application = self.application()
        self.error(self.post("student", "/api/clubs/1/applications", {"message": "重复申请"}), 409)
        self.error(self.post("other_leader", f"/api/applications/{application['id']}/review",
                             {"decision": "approve"}), 403)
        self.error(self.post("staff", f"/api/applications/{application['id']}/review",
                             {"decision": "approve"}), 403)
        self.data(self.post("leader", f"/api/applications/{application['id']}/review", {"decision": "approve"}))
        members = self.data(self.client("leader").get("/api/clubs/1/members"))
        self.assertTrue(any(member["user_id"] == 1 and member["active"] for member in members))
        self.assertEqual(self.data(self.client("student").get("/api/my/applications"))[0]["status"], "approved")
        self.error(self.post("student", "/api/clubs/1/applications", {"message": "已入社"}), 409)
        self.error(self.post("leader", f"/api/applications/{application['id']}/review", {"decision": "approve"}), 409)

    def test_rejection_requires_reason_and_does_not_add_member(self):
        application = self.application()
        endpoint = f"/api/applications/{application['id']}/review"
        self.error(self.post("leader", endpoint, {"decision": "reject", "reason": ""}), 400)
        self.data(self.post("leader", endpoint, {"decision": "reject", "reason": "本轮名额已满"}))
        members = self.data(self.client("leader").get("/api/clubs/1/members"))
        self.assertFalse(any(member["user_id"] == 1 for member in members))
        self.assertEqual(self.data(self.client("student").get("/api/my/applications"))[0]["status"], "rejected")

    def test_application_owner_can_cancel_then_reapply(self):
        application = self.application()
        endpoint = f"/api/applications/{application['id']}/cancel"
        self.error(self.post("member", endpoint), 403)
        self.data(self.post("student", endpoint))
        self.error(self.post("leader", f"/api/applications/{application['id']}/review", {"decision": "approve"}), 409)
        new_application = self.application()
        self.assertNotEqual(application["id"], new_application["id"])

    def test_other_club_leader_cannot_inspect_or_change_members(self):
        members = self.data(self.client("leader").get("/api/clubs/1/members"))
        member = next(member for member in members if member["user_id"] == 3)
        self.error(self.client("other_leader").get("/api/clubs/1/applications"), 403)
        self.error(self.client("other_leader").get("/api/clubs/1/members"), 403)
        self.error(self.patch("other_leader", f"/api/clubs/1/members/{member['id']}", {"active": False}), 403)
        self.assertTrue(next(value for value in self.data(self.client("leader").get("/api/clubs/1/members"))
                             if value["user_id"] == 3)["active"])

    def test_stopping_member_removes_organization_authority_but_keeps_history(self):
        members = self.data(self.client("leader").get("/api/clubs/1/members"))
        member = next(member for member in members if member["user_id"] == 3)
        self.data(self.client("member").get("/api/activities/2/registrations"))
        self.data(self.patch("leader", f"/api/clubs/1/members/{member['id']}", {"active": False}))
        self.error(self.client("member").get("/api/activities/2/registrations"), 403)
        self.error(self.post("member", "/api/activities/2/check-ins", {"user_id": 3}), 403)
        self.assertTrue(any(row["activity_id"] == 2 for row in self.data(self.client("member").get("/api/my/registrations"))))

    def test_current_leader_cannot_be_stopped_by_membership_endpoint(self):
        leader = next(value for value in self.data(self.client("leader").get("/api/clubs/1/members"))
                      if value["user_id"] == 2)
        self.error(self.patch("leader", f"/api/clubs/1/members/{leader['id']}", {"active": False}), 409)


class ActivityWorkflowTests(BusinessTestCase):
    def test_draft_is_hidden_until_approval_and_publication(self):
        activity = self.create_activity()
        activity_id = activity["id"]
        for client in [self.app.test_client(), self.client("student")]:
            self.assertFalse(any(value["id"] == activity_id for value in self.data(client.get("/api/activities"))))
            self.error(client.get(f"/api/activities/{activity_id}"), 404)
        self.assertEqual(self.data(self.client("leader").get(f"/api/activities/{activity_id}"))["status"], "Draft")
        self.error(self.transition("leader", activity_id, "publish"), 409)
        self.data(self.transition("leader", activity_id, "submit"))
        self.assertTrue(any(value["id"] == activity_id for value in self.data(self.client("staff").get("/api/my/activities"))))
        self.error(self.transition("leader", activity_id, "approve"), 403)
        self.error(self.transition("other_leader", activity_id, "publish"), 403)
        self.data(self.transition("staff", activity_id, "approve"))
        self.error(self.transition("staff", activity_id, "publish"), 403)
        self.data(self.transition("leader", activity_id, "publish"))
        self.assertTrue(any(value["id"] == activity_id for value in self.data(self.app.test_client().get("/api/activities"))))
        self.error(self.register("student", activity_id), 409)
        self.data(self.transition("leader", activity_id, "open_registration"))
        self.assertEqual(self.data(self.register("student", activity_id), 201)["status"], "confirmed")

    def test_rejected_activity_can_be_corrected_but_cannot_be_published(self):
        activity_id = self.create_activity()["id"]
        self.data(self.transition("leader", activity_id, "submit"))
        self.error(self.transition("staff", activity_id, "reject", reason=""), 400)
        self.data(self.transition("staff", activity_id, "reject", reason="活动安排需要完善"))
        self.error(self.transition("leader", activity_id, "publish"), 409)
        edited = self.data(self.patch("leader", f"/api/activities/{activity_id}", {"description": "补充安全与人员安排。"}))
        self.assertEqual(edited["status"], "Draft")
        self.data(self.transition("leader", activity_id, "submit"))
        self.assertEqual(self.data(self.transition("staff", activity_id, "approve"))["status"], "Approved")

    def test_cross_club_create_edit_and_task_management_are_rejected(self):
        self.error(self.post("other_leader", "/api/activities", self.activity_body()), 403)
        self.error(self.post("student", "/api/activities", self.activity_body()), 403)
        activity_id = self.create_activity()["id"]
        self.error(self.patch("other_leader", f"/api/activities/{activity_id}", {"title": "越权修改"}), 403)
        self.error(self.post("other_leader", f"/api/activities/{activity_id}/tasks", {
            "title": "越权任务", "assignee_id": 3, "due_time": (self.now + timedelta(hours=1)).isoformat()}), 403)

    def test_activity_validates_required_fields_time_zone_order_and_capacity(self):
        invalid = [
            {"title": ""}, {"capacity": 0}, {"capacity": -1}, {"capacity": True},
            {"start_time": "2030-06-01T15:00:00"},
            {"registration_deadline": (self.now + timedelta(hours=5)).isoformat()},
            {"end_time": (self.now + timedelta(hours=3)).isoformat()},
            {"title": "x" * 1001},
        ]
        for update in invalid:
            with self.subTest(update=update):
                self.error(self.post("leader", "/api/activities", self.activity_body(**update)), 400)

    def test_public_filters_combine_and_do_not_reveal_drafts(self):
        activity_id = self.open_activity(title="筛选专用摄影漫步", theme="测试主题")
        self.create_activity(title="筛选专用隐藏草稿", theme="测试主题")
        path = "/api/activities?q=筛选专用&theme=测试主题&club_id=1&date=2030-06-01"
        values = self.data(self.app.test_client().get(path))
        self.assertEqual([value["id"] for value in values], [activity_id])
        self.assertEqual(self.data(self.app.test_client().get(path.replace("q=筛选专用", "q=不存在"))), [])

    def test_date_filter_uses_requested_local_day_at_utc_midnight_boundary(self):
        activity_id = self.open_activity(
            title="跨时区日期专用活动",
            registration_deadline="2030-06-01T19:00:00+00:00",
            start_time="2030-06-01T20:00:00+00:00",
            end_time="2030-06-01T21:00:00+00:00")
        client = self.app.test_client()
        query = "/api/activities?q=跨时区日期专用活动"
        local = self.data(client.get(query + "&date=2030-06-02&utc_offset=480"))
        self.assertEqual([value["id"] for value in local], [activity_id])
        self.assertEqual(self.data(client.get(query + "&date=2030-06-01&utc_offset=480")), [])
        utc = self.data(client.get(query + "&date=2030-06-01"))
        self.assertEqual([value["id"] for value in utc], [activity_id])

    def test_deadline_start_and_end_lifecycle_use_exact_instants_and_leave_drafts_unchanged(self):
        activity_id = self.open_activity()
        draft_id = self.create_activity()["id"]
        for hours, status in [(2, "RegistrationClosed"), (3, "InProgress"), (4, "Finished")]:
            self.advance(datetime(2030, 6, 1, 12, tzinfo=timezone.utc) + timedelta(hours=hours))
            self.assertEqual(self.data(self.app.test_client().get(f"/api/activities/{activity_id}"))["status"], status)
            self.assertEqual(self.data(self.client("leader").get(f"/api/activities/{draft_id}"))["status"], "Draft")
        self.assertEqual(self.data(self.transition("leader", activity_id, "archive"))["status"], "Archived")

    def test_text_input_is_served_as_json_not_executable_html(self):
        payload = "<img src=x onerror=alert(1)>"
        activity = self.create_activity(title=payload, description="<script>alert(1)</script>")
        response = self.client("leader").get(f"/api/activities/{activity['id']}")
        self.assertEqual(response.mimetype, "application/json")
        self.assertEqual(self.data(response)["title"], payload)


class RegistrationTests(BusinessTestCase):
    def test_duplicate_registration_fails_without_duplicate_notification(self):
        activity_id = self.open_activity()
        before = len(self.data(self.client("student").get("/api/notifications")))
        registration = self.data(self.register("student", activity_id), 201)
        self.error(self.register("student", activity_id), 409)
        rows = self.data(self.client("student").get("/api/my/registrations"))
        self.assertEqual([row["id"] for row in rows if row["activity_id"] == activity_id], [registration["id"]])
        after = len(self.data(self.client("student").get("/api/notifications")))
        self.assertEqual(after - before, 1)

    def test_concurrent_requests_do_not_exceed_capacity(self):
        activity_id = self.open_activity(capacity=1, waitlist_enabled=False)
        accounts = ["student", "leader", "member", "other_leader"]
        participants = [self.login(name, remember=False) for name in accounts]
        barrier = threading.Barrier(len(participants))

        def participate(participant):
            client, token = participant
            barrier.wait(timeout=10)
            response = client.post(f"/api/activities/{activity_id}/registrations", json={},
                                   headers={"X-CSRF-Token": token})
            return response.status_code, response.get_json()

        with ThreadPoolExecutor(max_workers=len(participants)) as executor:
            results = list(executor.map(participate, participants))
        self.assertEqual(sum(status == 201 for status, _ in results), 1, results)
        self.assertTrue(all(status in (201, 409) for status, _ in results), results)
        activity = self.data(self.app.test_client().get(f"/api/activities/{activity_id}"))
        self.assertEqual(activity["registered_count"], 1)
        self.assertEqual(activity["waitlist_count"], 0)
        rows = self.data(self.client("leader").get(f"/api/activities/{activity_id}/registrations"))
        self.assertEqual(sum(row["status"] == "confirmed" for row in rows), 1)

    def test_simultaneous_same_student_requests_create_one_effective_record(self):
        activity_id = self.open_activity(capacity=3)
        participants = [self.login("student", remember=False) for _ in range(3)]
        barrier = threading.Barrier(len(participants))

        def participate(participant):
            client, token = participant
            barrier.wait(timeout=10)
            return client.post(f"/api/activities/{activity_id}/registrations", json={},
                               headers={"X-CSRF-Token": token}).status_code

        with ThreadPoolExecutor(max_workers=3) as executor:
            statuses = list(executor.map(participate, participants))
        self.assertEqual(statuses.count(201), 1, statuses)
        self.assertEqual(statuses.count(409), 2, statuses)
        rows = self.data(self.client("student").get("/api/my/registrations"))
        self.assertEqual(sum(row["activity_id"] == activity_id and row["status"] == "confirmed" for row in rows), 1)

    def test_waitlist_cancellation_is_skipped_and_first_effective_waiter_is_promoted_once(self):
        activity_id = self.open_activity(capacity=1)
        first = self.data(self.register("student", activity_id), 201)
        skipped = self.data(self.register("other_leader", activity_id), 201)
        second = self.data(self.register("member", activity_id), 201)
        third = self.data(self.register("leader", activity_id), 201)
        self.assertEqual([first["status"], skipped["status"], second["status"], third["status"]],
                         ["confirmed", "waitlisted", "waitlisted", "waitlisted"])
        self.data(self.post("other_leader", f"/api/registrations/{skipped['id']}/cancel"))
        before = len(self.data(self.client("member").get("/api/notifications")))
        self.data(self.post("student", f"/api/registrations/{first['id']}/cancel"))
        rows = self.data(self.client("leader").get(f"/api/activities/{activity_id}/registrations"))
        states = {row["id"]: row["status"] for row in rows}
        self.assertEqual(states[first["id"]], "cancelled")
        self.assertEqual(states[skipped["id"]], "cancelled")
        self.assertEqual(states[second["id"]], "confirmed")
        self.assertEqual(states[third["id"]], "waitlisted")
        self.error(self.post("student", f"/api/registrations/{first['id']}/cancel"), 409)
        self.assertEqual(len(self.data(self.client("member").get("/api/notifications"))) - before, 1)
        self.assertEqual(self.data(self.app.test_client().get(f"/api/activities/{activity_id}"))["registered_count"], 1)

    def test_concurrent_cancellation_and_registration_preserve_waitlist_priority(self):
        activity_id = self.open_activity(capacity=1)
        first = self.data(self.register("student", activity_id), 201)
        waiter = self.data(self.register("member", activity_id), 201)
        cancel_client, cancel_token = self.login("student", remember=False)
        new_client, new_token = self.login("other_leader", remember=False)
        barrier = threading.Barrier(2)

        def cancel():
            barrier.wait(timeout=10)
            return cancel_client.post(f"/api/registrations/{first['id']}/cancel", json={},
                                      headers={"X-CSRF-Token": cancel_token}).status_code

        def register_new():
            barrier.wait(timeout=10)
            return new_client.post(f"/api/activities/{activity_id}/registrations", json={},
                                   headers={"X-CSRF-Token": new_token}).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(cancel), executor.submit(register_new)]
            self.assertEqual([future.result() for future in futures], [200, 201])
        rows = self.data(self.client("leader").get(f"/api/activities/{activity_id}/registrations"))
        confirmed = [row for row in rows if row["status"] == "confirmed"]
        self.assertEqual([row["id"] for row in confirmed], [waiter["id"]])
        self.assertEqual(next(row for row in rows if row["user_id"] == 4)["status"], "waitlisted")

    def test_cancellation_and_registration_are_denied_exactly_at_deadline(self):
        activity_id = self.open_activity(capacity=1)
        first = self.data(self.register("student", activity_id), 201)
        self.data(self.register("member", activity_id), 201)
        self.advance(self.now + timedelta(hours=2))
        self.error(self.register("other_leader", activity_id), 409)
        self.error(self.post("student", f"/api/registrations/{first['id']}/cancel"), 409)
        activity = self.data(self.app.test_client().get(f"/api/activities/{activity_id}"))
        self.assertEqual(activity["registered_count"], 1)
        self.assertEqual(activity["waitlist_count"], 1)

    def test_cancellation_is_personal_and_freed_capacity_can_be_reused(self):
        activity_id = self.open_activity(capacity=1, waitlist_enabled=False)
        registration = self.data(self.register("student", activity_id), 201)
        self.error(self.post("member", f"/api/registrations/{registration['id']}/cancel"), 403)
        self.data(self.post("student", f"/api/registrations/{registration['id']}/cancel"))
        self.assertEqual(self.data(self.register("member", activity_id), 201)["status"], "confirmed")

    def test_cancelled_activity_notifies_participants_and_never_progresses(self):
        activity_id = self.open_activity(capacity=1)
        self.data(self.register("student", activity_id), 201)
        self.data(self.register("member", activity_id), 201)
        before = {name: len(self.data(self.client(name).get("/api/notifications"))) for name in ["student", "member"]}
        self.data(self.transition("leader", activity_id, "cancel", reason="天气原因"))
        self.error(self.register("other_leader", activity_id), 409)
        for name in ["student", "member"]:
            self.assertEqual(len(self.data(self.client(name).get("/api/notifications"))) - before[name], 1)
        self.advance(self.now + timedelta(hours=5))
        self.assertEqual(self.data(self.app.test_client().get(f"/api/activities/{activity_id}"))["status"], "Cancelled")
        self.error(self.post("leader", f"/api/activities/{activity_id}/check-ins", {"user_id": 1}), 409)


class CheckInTaskAndNotificationTests(BusinessTestCase):
    def test_checkin_requires_in_progress_confirmed_registration_and_club_authority(self):
        activity_id = self.open_activity(capacity=1)
        self.data(self.register("student", activity_id), 201)
        self.data(self.register("other_leader", activity_id), 201)
        self.error(self.post("member", f"/api/activities/{activity_id}/check-ins", {"user_id": 1}), 409)
        self.advance(self.now + timedelta(hours=3))
        self.error(self.post("other_leader", f"/api/activities/{activity_id}/check-ins", {"user_id": 1}), 403)
        self.error(self.post("member", f"/api/activities/{activity_id}/check-ins", {"user_id": 4}), 409)
        self.data(self.post("member", f"/api/activities/{activity_id}/check-ins", {"user_id": 1}))
        self.error(self.post("leader", f"/api/activities/{activity_id}/check-ins", {"user_id": 1}), 409)
        rows = self.data(self.client("student").get("/api/my/registrations"))
        self.assertTrue(next(row for row in rows if row["activity_id"] == activity_id)["checked_in"])
        self.error(self.client("student").get(f"/api/activities/{activity_id}/registrations"), 403)

    def test_tasks_assigned_only_to_active_members_and_updates_respect_ownership(self):
        activity_id = self.create_activity()["id"]
        body = {"title": "检查摄影设备", "assignee_id": 3,
                "due_time": (self.now + timedelta(hours=1)).isoformat()}
        self.error(self.post("leader", f"/api/activities/{activity_id}/tasks", {**body, "assignee_id": 4}), 409)
        before = len(self.data(self.client("member").get("/api/notifications")))
        task = self.data(self.post("leader", f"/api/activities/{activity_id}/tasks", body), 201)
        for name in ["student", "other_leader", "staff"]:
            self.error(self.patch(name, f"/api/tasks/{task['id']}", {"status": "done"}), 403)
            self.assertFalse(any(value["id"] == task["id"] for value in self.data(self.client(name).get("/api/tasks"))))
        self.assertEqual(len(self.data(self.client("member").get("/api/notifications"))) - before, 1)
        self.error(self.patch("member", f"/api/tasks/{task['id']}", {"status": "unknown"}), 400)
        self.assertEqual(self.data(self.patch("member", f"/api/tasks/{task['id']}", {"status": "in_progress"}))["status"], "in_progress")
        self.assertEqual(self.data(self.patch("member", f"/api/tasks/{task['id']}", {"status": "done"}))["status"], "done")
        self.error(self.patch("member", f"/api/tasks/{task['id']}", {"status": "todo"}), 409)
        self.error(self.patch("member", f"/api/tasks/{task['id']}", {"status": "in_progress"}), 409)

    def test_stopping_member_invalidates_existing_task_authority(self):
        activity_id = self.create_activity()["id"]
        task = self.data(self.post("leader", f"/api/activities/{activity_id}/tasks", {
            "title": "停用前任务", "assignee_id": 3,
            "due_time": (self.now + timedelta(hours=1)).isoformat()}), 201)
        member = next(value for value in self.data(self.client("leader").get("/api/clubs/1/members")) if value["user_id"] == 3)
        self.data(self.patch("leader", f"/api/clubs/1/members/{member['id']}", {"active": False}))
        self.error(self.patch("member", f"/api/tasks/{task['id']}", {"status": "in_progress"}), 403)

    def test_notifications_are_private_and_mark_read_is_idempotent(self):
        activity_id = self.open_activity()
        self.data(self.register("student", activity_id), 201)
        notification = self.data(self.client("student").get("/api/notifications"))[0]
        endpoint = f"/api/notifications/{notification['id']}/read"
        self.error(self.post("member", endpoint), 403)
        self.data(self.post("student", endpoint))
        self.data(self.post("student", endpoint))
        values = self.data(self.client("student").get("/api/notifications"))
        self.assertTrue(next(value for value in values if value["id"] == notification["id"])["read"])


class ClubGovernanceTests(BusinessTestCase):
    def test_applicant_does_not_get_formal_club_or_leadership_before_staff_approval(self):
        before = self.data(self.app.test_client().get("/api/clubs"))
        request = self.data(self.post("student", "/api/club-registrations", {
            "name": "演示天文社", "description": "校园星空观察。"}), 201)
        self.assertEqual(self.data(self.app.test_client().get("/api/clubs")), before)
        self.assertFalse(any(value.get("role") == "leader" for value in self.data(self.client("student").get("/api/my/clubs"))))
        self.error(self.post("leader", f"/api/club-registrations/{request['id']}/review", {"decision": "approve"}), 403)
        self.data(self.post("staff", f"/api/club-registrations/{request['id']}/review", {"decision": "approve"}))
        clubs = self.data(self.app.test_client().get("/api/clubs"))
        club = next(value for value in clubs if value["name"] == "演示天文社")
        owned = self.data(self.client("student").get("/api/my/clubs"))
        self.assertTrue(any(value["id"] == club["id"] and value["role"] == "leader" for value in owned))
        self.error(self.post("staff", f"/api/club-registrations/{request['id']}/review", {"decision": "approve"}), 409)

    def test_pending_club_registration_is_unique_and_rejection_requires_reason(self):
        request = self.data(self.post("student", "/api/club-registrations", {
            "name": "演示天文社", "description": "校园星空观察。"}), 201)
        self.error(self.post("student", "/api/club-registrations", {
            "name": "演示天文社", "description": "重复备案。"}), 409)
        endpoint = f"/api/club-registrations/{request['id']}/review"
        self.error(self.post("staff", endpoint, {"decision": "reject", "reason": ""}), 400)
        self.data(self.post("staff", endpoint, {"decision": "reject", "reason": "活动场所计划需补充"}))
        self.assertFalse(any(value["name"] == "演示天文社" for value in self.data(self.app.test_client().get("/api/clubs"))))
        records = self.data(self.client("student").get("/api/club-registrations"))
        self.assertEqual(records[0]["status"], "rejected")
        self.assertEqual(records[0]["reason"], "活动场所计划需补充")
        self.assertEqual(self.data(self.client("member").get("/api/club-registrations")), [])

    def test_leadership_change_requires_staff_and_active_member_then_changes_authority(self):
        self.error(self.patch("leader", "/api/clubs/1/governance", {"leader_id": 3}), 403)
        self.error(self.patch("staff", "/api/clubs/1/governance", {"leader_id": 4}), 409)
        self.data(self.patch("staff", "/api/clubs/1/governance", {"leader_id": 3}))
        self.error(self.post("leader", "/api/activities", self.activity_body()), 403)
        self.data(self.post("member", "/api/activities", self.activity_body()), 201)
        members = self.data(self.client("member").get("/api/clubs/1/members"))
        self.assertEqual(sum(value["role"] == "leader" and value["active"] for value in members), 1)
        self.assertEqual(next(value for value in members if value["user_id"] == 3)["role"], "leader")
        records = self.data(self.client("staff").get("/api/audit"))
        self.assertTrue(any(value["entity_type"] == "club" and value["entity_id"] == 1 for value in records))

    def test_disabled_club_blocks_business_writes_but_personal_cancellation_remains(self):
        activity_id = self.open_activity()
        registration = self.data(self.register("student", activity_id), 201)
        self.data(self.patch("staff", "/api/clubs/1/governance", {"status": "disabled"}))
        self.error(self.post("leader", "/api/activities", self.activity_body()), 409)
        self.error(self.register("member", activity_id), 409)
        self.error(self.post("other_leader", "/api/clubs/1/applications", {"message": "申请"}), 409)
        self.data(self.post("student", f"/api/registrations/{registration['id']}/cancel"))
        self.assertTrue(any(value["activity_id"] == activity_id for value in self.data(self.client("student").get("/api/my/registrations"))))

    def test_audit_and_runtime_logs_require_staff_and_do_not_leak_authentication_material(self):
        activity_id = self.create_activity()["id"]
        self.data(self.transition("leader", activity_id, "submit"))
        self.data(self.transition("staff", activity_id, "approve"))
        for path in ["/api/audit", "/api/logs"]:
            self.error(self.client("leader").get(path), 403)
            self.error(self.client("student").get(path), 403)
            records = self.data(self.client("staff").get(path))
            self.assertIsInstance(records, list)
            text = str(records).lower()
            for secret in ["demo12345", "password_hash", "csrf_token", "isolated-test-secret"]:
                self.assertNotIn(secret, text)
        audit = self.data(self.client("staff").get("/api/audit"))
        self.assertTrue(any(value["entity_type"] == "activity" and value["entity_id"] == activity_id for value in audit))


class FaultAndRecoveryTests(BusinessTestCase):
    def test_notification_failure_rolls_back_registration_and_capacity(self):
        activity_id = self.open_activity(capacity=1)
        before = self.data(self.client("student").get("/api/notifications"))
        with patch("campus_clubs.routes.notify", side_effect=RuntimeError("sensitive-diagnostic-marker")):
            response = self.register("student", activity_id)
        self.error(response, 500)
        self.assertNotIn("sensitive-diagnostic-marker", response.get_data(as_text=True))
        rows = self.data(self.client("student").get("/api/my/registrations"))
        self.assertFalse(any(row["activity_id"] == activity_id for row in rows))
        self.assertEqual(self.data(self.client("student").get("/api/notifications")), before)
        self.assertEqual(self.data(self.app.test_client().get(f"/api/activities/{activity_id}"))["registered_count"], 0)
        self.assertEqual(self.data(self.register("member", activity_id), 201)["status"], "confirmed")

    def test_failed_transfer_notification_rolls_back_cancellation_and_promotion(self):
        activity_id = self.open_activity(capacity=1)
        first = self.data(self.register("student", activity_id), 201)
        waiter = self.data(self.register("member", activity_id), 201)
        before = {name: self.data(self.client(name).get("/api/notifications")) for name in ["student", "member"]}
        from campus_clubs import routes
        notify = routes.notify

        def fail_promotion_notification(user_id, title, message):
            if user_id == 3:
                raise RuntimeError("sensitive-diagnostic-marker")
            return notify(user_id, title, message)

        with patch("campus_clubs.routes.notify", side_effect=fail_promotion_notification):
            self.error(self.post("student", f"/api/registrations/{first['id']}/cancel"), 500)
        rows = self.data(self.client("leader").get(f"/api/activities/{activity_id}/registrations"))
        self.assertEqual(next(row for row in rows if row["id"] == first["id"])["status"], "confirmed")
        self.assertEqual(next(row for row in rows if row["id"] == waiter["id"])["status"], "waitlisted")
        for name in before:
            self.assertEqual(self.data(self.client(name).get("/api/notifications")), before[name])
        self.data(self.post("student", f"/api/registrations/{first['id']}/cancel"))
        self.assertEqual(self.data(self.app.test_client().get(f"/api/activities/{activity_id}"))["registered_count"], 1)

    def test_runtime_log_records_four_failure_categories_without_sensitive_details(self):
        client = self.app.test_client()
        token = self.data(client.get("/api/session"))["csrf_token"]
        self.error(client.post("/api/login", json={"username": "student", "password": "private-bad-password"},
                               headers={"X-CSRF-Token": token}), 401)
        self.error(self.client("student").get("/api/audit"), 403)
        activity_id = self.open_activity()
        with patch("campus_clubs.routes.notify", side_effect=RuntimeError("sensitive-diagnostic-marker")):
            self.error(self.register("student", activity_id), 500)
        from campus_clubs.service import tick
        with self.app.app_context():
            with patch("campus_clubs.service.refresh_lifecycle", side_effect=RuntimeError("sensitive-background-marker")):
                with self.assertRaises(RuntimeError):
                    tick()
        records = self.data(self.client("staff").get("/api/logs"))
        categories = {record["event_type"] for record in records}
        self.assertTrue({"login_failed", "unauthorized", "system_error", "background_task_failure"}.issubset(categories), categories)
        text = str(records)
        for sensitive in ["private-bad-password", "sensitive-diagnostic-marker", "sensitive-background-marker", token]:
            self.assertNotIn(sensitive, text)

    def cli(self, *arguments):
        runner = Path(__file__).resolve().parents[1] / "run.py"
        return subprocess.run([sys.executable, "-X", "utf8", str(runner), "--database", self.app.config["DATABASE"], *map(str, arguments)],
                              capture_output=True, text=True, encoding="utf-8", timeout=30)

    def test_backup_restore_preserves_committed_business_records(self):
        activity_id = self.open_activity()
        registration = self.data(self.register("student", activity_id), 201)
        backup = Path(self.directory.name) / "snapshot.sqlite3"
        restored = Path(self.directory.name) / "restored.sqlite3"
        result = self.cli("backup", backup)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.data(self.post("student", f"/api/registrations/{registration['id']}/cancel"))
        result = self.cli("restore", backup, restored)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        restored_app = create_app({"TESTING": True, "DATABASE": str(restored), "SECRET_KEY": "independent-restore-check",
                                   "NOW": lambda: self.now})
        with restored_app.app_context():
            row = get_db().execute("SELECT status FROM registrations WHERE id=?", (registration["id"],)).fetchone()
            self.assertEqual(row["status"], "confirmed")
            self.assertEqual(get_db().execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(get_db().execute("SELECT count(*) FROM users").fetchone()[0], 5)
        current = self.data(self.client("student").get("/api/my/registrations"))
        self.assertEqual(next(row for row in current if row["id"] == registration["id"])["status"], "cancelled")

    def test_backup_and_restore_refuse_to_overwrite_existing_targets(self):
        backup = Path(self.directory.name) / "snapshot.sqlite3"
        self.assertEqual(self.cli("backup", backup).returncode, 0)
        original = backup.read_bytes()
        self.assertNotEqual(self.cli("backup", backup).returncode, 0)
        self.assertEqual(backup.read_bytes(), original)
        existing = Path(self.directory.name) / "existing.sqlite3"
        existing.write_bytes(b"existing target must stay unchanged")
        self.assertNotEqual(self.cli("restore", backup, existing).returncode, 0)
        self.assertEqual(existing.read_bytes(), b"existing target must stay unchanged")

    def test_restore_rejects_corrupt_or_unrelated_databases_without_creating_target(self):
        import sqlite3
        corrupt = Path(self.directory.name) / "corrupt.sqlite3"
        corrupt.write_bytes(b"not a sqlite database")
        unrelated = Path(self.directory.name) / "unrelated.sqlite3"
        with closing(sqlite3.connect(unrelated)) as connection:
            connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
            connection.commit()
        for source in [corrupt, unrelated, Path(self.directory.name) / "missing.sqlite3"]:
            with self.subTest(source=source.name):
                target = Path(self.directory.name) / (source.stem + "-restored.sqlite3")
                self.assertNotEqual(self.cli("restore", source, target).returncode, 0)
                self.assertFalse(target.exists())

    def test_demo_initialization_refuses_to_overwrite_existing_data(self):
        result = self.cli("init-demo")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.data(self.app.test_client().get("/api/clubs"))), 2)
        self.assertEqual(self.data(self.client("member").get("/api/my/registrations"))[0]["activity_id"], 2)


if __name__ == "__main__":
    unittest.main()
