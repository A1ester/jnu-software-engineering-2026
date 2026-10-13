"""Acceptance scenarios for resources, feedback, statistics and personal work."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import csv
import io
import threading
from unittest.mock import patch
from werkzeug.security import check_password_hash

# The imported fixture has no test methods, so discovery does not repeat the core suite.
from test_business import BusinessTestCase
from campus_clubs.db import get_db


class ExtensionTestCase(BusinessTestCase):
    def submitted_activity(self, username="leader", **updates):
        activity = self.create_activity(username=username, **updates)
        self.data(self.transition(username, activity["id"], "submit"))
        return activity["id"]

    def venue_request(self, activity_id, username="leader", venue_id=1, start=None, end=None):
        return self.post(username, f"/api/activities/{activity_id}/venue-applications", {
            "venue_id": venue_id,
            "start_time": start or (self.now + timedelta(hours=3)).isoformat(),
            "end_time": end or (self.now + timedelta(hours=4)).isoformat(),
        })

    def venue_review(self, request_id, username="staff", decision="approve", reason=""):
        return self.post(username, f"/api/venue-applications/{request_id}/review", {
            "decision": decision, "reason": reason,
        })

    def finished_activity(self, title="反馈与统计测试活动"):
        activity_id = self.open_activity(title=title, capacity=2)
        student = self.data(self.register("student", activity_id), 201)
        member = self.data(self.register("member", activity_id), 201)
        self.advance(self.now + timedelta(hours=3))
        self.data(self.post("leader", f"/api/activities/{activity_id}/check-ins", {"user_id": 1}))
        self.advance(self.now + timedelta(hours=1))
        self.assertEqual(self.data(self.app.test_client().get(f"/api/activities/{activity_id}"))["status"], "Finished")
        return activity_id, student, member


class PasswordStorageTests(ExtensionTestCase):
    def test_password_storage_uses_independently_salted_hashes_and_checks_credentials(self):
        with self.app.app_context():
            hashes = [row["password_hash"] for row in get_db().execute("SELECT password_hash FROM users ORDER BY id")]
        self.assertEqual(len(hashes), 5)
        self.assertEqual(len(set(hashes)), 5)
        for stored in hashes:
            self.assertNotIn("Demo12345!", stored)
            self.assertTrue(stored.startswith("scrypt:"))
            self.assertTrue(check_password_hash(stored, "Demo12345!"))
            self.assertFalse(check_password_hash(stored, "incorrect-password"))


class VenueTests(ExtensionTestCase):
    def test_venue_request_separates_owning_leader_from_staff_and_other_clubs(self):
        draft_id = self.create_activity()["id"]
        self.error(self.venue_request(draft_id), 409)
        activity_id = self.submitted_activity()
        for name in ["student", "other_leader", "staff"]:
            self.error(self.venue_request(activity_id, username=name), 403)
        request = self.data(self.venue_request(activity_id), 201)
        self.assertTrue(any(value["id"] == request["id"] for value in self.data(self.client("leader").get("/api/venue-applications"))))
        self.assertEqual(self.data(self.client("other_leader").get("/api/venue-applications")), [])
        self.assertTrue(any(value["id"] == request["id"] for value in self.data(self.client("staff").get("/api/venue-applications"))))
        self.error(self.venue_review(request["id"], username="leader"), 403)
        self.assertEqual(self.data(self.venue_review(request["id"]))["status"], "approved")

    def test_venue_validates_interval_bounds_and_rejects_duplicate_effective_request(self):
        activity_id = self.submitted_activity()
        base = {"venue_id": 1, "start_time": (self.now + timedelta(hours=3)).isoformat(),
                "end_time": (self.now + timedelta(hours=4)).isoformat()}
        invalid = [
            {"venue_id": True},
            {"start_time": "2030-06-01T15:00:00"},
            {"start_time": (self.now + timedelta(hours=2)).isoformat()},
            {"end_time": (self.now + timedelta(hours=5)).isoformat()},
            {"end_time": base["start_time"]},
        ]
        for update in invalid:
            with self.subTest(update=update):
                self.error(self.post("leader", f"/api/activities/{activity_id}/venue-applications", {**base, **update}), 400)
        self.error(self.venue_request(activity_id, venue_id=999), 404)
        self.data(self.venue_request(activity_id), 201)
        self.error(self.venue_request(activity_id), 409)

    def test_simultaneous_overlapping_approvals_accept_only_one_reservation(self):
        first_activity = self.submitted_activity()
        second_activity = self.submitted_activity(username="other_leader", club_id=2, title="读书社会场申请")
        requests = [self.data(self.venue_request(first_activity), 201),
                    self.data(self.venue_request(second_activity, username="other_leader"), 201)]
        participants = [self.login("staff", remember=False) for _ in requests]
        barrier = threading.Barrier(2)

        def approve(pair):
            request, (client, token) = pair
            barrier.wait(timeout=10)
            response = client.post(f"/api/venue-applications/{request['id']}/review",
                                   json={"decision": "approve", "reason": ""}, headers={"X-CSRF-Token": token})
            return response.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(approve, zip(requests, participants)))
        self.assertEqual(sorted(statuses), [200, 409])
        values = self.data(self.client("staff").get("/api/venue-applications"))
        selected = [value for value in values if value["id"] in {request["id"] for request in requests}]
        self.assertEqual(sorted(value["status"] for value in selected), ["approved", "pending"])
        approved = next(value for value in selected if value["status"] == "approved")
        self.error(self.venue_review(approved["id"]), 409)

    def test_adjacent_intervals_and_different_venues_can_both_be_approved(self):
        first_id = self.submitted_activity()
        second_id = self.submitted_activity(title="相邻时间段活动",
                                            start_time=(self.now + timedelta(hours=4)).isoformat(),
                                            end_time=(self.now + timedelta(hours=5)).isoformat())
        first = self.data(self.venue_request(first_id), 201)
        adjacent = self.data(self.venue_request(second_id, start=(self.now + timedelta(hours=4)).isoformat(),
                                                end=(self.now + timedelta(hours=5)).isoformat()), 201)
        other_venue = self.data(self.venue_request(first_id, venue_id=2), 201)
        for request in [first, adjacent, other_venue]:
            self.assertEqual(self.data(self.venue_review(request["id"]))["status"], "approved")

    def test_rejection_requires_reason_and_cancelled_activity_cannot_be_approved(self):
        activity_id = self.submitted_activity()
        request = self.data(self.venue_request(activity_id), 201)
        self.error(self.venue_review(request["id"], decision="reject"), 400)
        rejected = self.data(self.venue_review(request["id"], decision="reject", reason="设备维护"))
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(rejected["reason"], "设备维护")
        open_id = self.open_activity()
        pending = self.data(self.venue_request(open_id), 201)
        self.data(self.transition("leader", open_id, "cancel", reason="安排调整"))
        self.error(self.venue_review(pending["id"]), 409)
        self.assertEqual(self.data(self.venue_review(pending["id"], decision="reject", reason="关联活动已取消"))["status"], "rejected")

    def test_notification_failure_does_not_reserve_venue_or_consume_pending_request(self):
        activity_id = self.submitted_activity()
        request = self.data(self.venue_request(activity_id), 201)
        before = self.data(self.client("leader").get("/api/notifications"))
        with patch("campus_clubs.extensions.notify", side_effect=RuntimeError("private-venue-diagnostic")):
            self.error(self.venue_review(request["id"]), 500)
        values = self.data(self.client("staff").get("/api/venue-applications"))
        self.assertEqual(next(value for value in values if value["id"] == request["id"])["status"], "pending")
        self.assertEqual(self.data(self.client("leader").get("/api/notifications")), before)
        self.assertEqual(self.data(self.venue_review(request["id"]))["status"], "approved")


class MaterialsTests(ExtensionTestCase):
    def test_materials_are_private_and_managed_only_by_owning_leader(self):
        activity_id = self.create_activity()["id"]
        for name in ["student", "member", "other_leader", "staff"]:
            self.error(self.post(name, f"/api/activities/{activity_id}/materials", {"name": "三脚架", "quantity": 2}), 403)
        material = self.data(self.post("leader", f"/api/activities/{activity_id}/materials", {"name": "三脚架", "quantity": 2}), 201)
        self.assertEqual(material["status"], "requested")
        for name in ["student", "member", "other_leader"]:
            self.error(self.client(name).get(f"/api/activities/{activity_id}/materials"), 403)
            self.error(self.patch(name, f"/api/materials/{material['id']}", {"status": "ready"}), 403)
        self.assertTrue(any(value["id"] == material["id"] for value in self.data(self.client("staff").get(f"/api/activities/{activity_id}/materials"))))
        self.assertEqual(self.data(self.patch("leader", f"/api/materials/{material['id']}", {"status": "preparing"}))["status"], "preparing")
        self.assertEqual(self.data(self.patch("leader", f"/api/materials/{material['id']}", {"status": "ready"}))["status"], "ready")

    def test_materials_validate_names_quantities_status_and_disabled_club(self):
        activity_id = self.create_activity()["id"]
        for body in [{"name": "", "quantity": 1}, {"name": "设备", "quantity": 0},
                     {"name": "设备", "quantity": True}, {"name": "设备", "quantity": 10001}]:
            with self.subTest(body=body):
                self.error(self.post("leader", f"/api/activities/{activity_id}/materials", body), 400)
        material = self.data(self.post("leader", f"/api/activities/{activity_id}/materials", {"name": "摄影灯", "quantity": 1}), 201)
        self.error(self.patch("leader", f"/api/materials/{material['id']}", {"status": "delivered"}), 400)
        self.data(self.patch("staff", "/api/clubs/1/governance", {"status": "disabled"}))
        self.error(self.patch("leader", f"/api/materials/{material['id']}", {"status": "ready"}), 409)


class FeedbackAndStatisticsTests(ExtensionTestCase):
    def test_feedback_requires_finished_activity_and_personal_checkin_and_is_unique(self):
        activity_id = self.open_activity()
        self.data(self.register("student", activity_id), 201)
        self.data(self.register("member", activity_id), 201)
        body = {"rating": 4, "comment": "活动安排清楚。"}
        self.error(self.post("student", f"/api/activities/{activity_id}/feedback", body), 409)
        self.advance(self.now + timedelta(hours=3))
        self.data(self.post("leader", f"/api/activities/{activity_id}/check-ins", {"user_id": 1}))
        self.error(self.post("student", f"/api/activities/{activity_id}/feedback", body), 409)
        self.advance(self.now + timedelta(hours=1))
        self.error(self.post("member", f"/api/activities/{activity_id}/feedback", body), 403)
        self.error(self.post("other_leader", f"/api/activities/{activity_id}/feedback", body), 403)
        feedback = self.data(self.post("student", f"/api/activities/{activity_id}/feedback", body), 201)
        self.assertEqual(feedback["rating"], 4)
        self.error(self.post("student", f"/api/activities/{activity_id}/feedback", body), 409)
        self.assertEqual(self.data(self.client("student").get(f"/api/activities/{activity_id}"))["my_feedback"]["rating"], 4)
        self.assertIsNone(self.data(self.client("member").get(f"/api/activities/{activity_id}"))["my_feedback"])

    def test_feedback_validates_integer_rating_and_comment_length(self):
        activity_id, _, _ = self.finished_activity()
        for body in [{"rating": 0, "comment": "反馈"}, {"rating": 6, "comment": "反馈"},
                     {"rating": True, "comment": "反馈"}, {"rating": 3.5, "comment": "反馈"},
                     {"rating": 5, "comment": "x" * 2001}]:
            with self.subTest(body=body):
                self.error(self.post("student", f"/api/activities/{activity_id}/feedback", body), 400)
        self.data(self.post("student", f"/api/activities/{activity_id}/feedback", {"rating": 5, "comment": "谢谢组织。"}), 201)

    def test_finished_statistics_match_effective_registrations_checkins_and_feedback(self):
        activity_id = self.open_activity(capacity=2)
        self.data(self.register("student", activity_id), 201)
        removed = self.data(self.register("member", activity_id), 201)
        self.data(self.register("other_leader", activity_id), 201)
        self.data(self.post("member", f"/api/registrations/{removed['id']}/cancel"))
        self.advance(self.now + timedelta(hours=3))
        self.data(self.post("leader", f"/api/activities/{activity_id}/check-ins", {"user_id": 1}))
        self.advance(self.now + timedelta(hours=1))
        self.data(self.post("student", f"/api/activities/{activity_id}/feedback", {"rating": 4, "comment": "很满意"}), 201)
        statistics = self.data(self.client("leader").get("/api/clubs/1/statistics"))
        value = next(value for value in statistics["activities"] if value["id"] == activity_id)
        self.assertEqual((value["registration_count"], value["check_in_count"], value["feedback_count"]), (2, 1, 1))
        self.assertNotIn(1, [value["id"] for value in statistics["activities"]])
        for name in ["student", "other_leader"]:
            self.error(self.client(name).get("/api/clubs/1/statistics"), 403)
            self.error(self.client(name).get("/api/clubs/1/statistics.csv"), 403)
        self.assertEqual(self.data(self.client("staff").get("/api/clubs/1/statistics")), statistics)
        text = str(statistics)
        for private in ["演示学生", "摄影社演示成员", "password", "user_id", "display_name"]:
            self.assertNotIn(private, text)

    def test_csv_export_preserves_statistics_and_neutralizes_spreadsheet_formulas(self):
        title = '=HYPERLINK("https://invalid.example","演示标题")'
        activity_id, _, _ = self.finished_activity(title=title)
        response = self.client("leader").get("/api/clubs/1/statistics.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("csv", response.mimetype)
        content = response.data.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(content)))
        row = next(row for row in rows if str(activity_id) in row and any(title in cell for cell in row))
        title_cell = next(cell for cell in row if title in cell)
        self.assertEqual(title_cell, "'" + title)
        self.assertEqual(row, [str(activity_id), "'" + title, "Finished", "2", "1", "0"])
        statistics = self.data(self.client("leader").get("/api/clubs/1/statistics"))
        current = next(value for value in statistics["activities"] if value["id"] == activity_id)
        self.assertEqual([int(value) for value in row[-3:]],
                         [current["registration_count"], current["check_in_count"], current["feedback_count"]])
        self.assertTrue(all(not cell.lstrip().startswith(("=", "+", "-", "@")) for cell in row))
        for private in ["演示学生", "摄影社演示成员", "Demo12345", "username", "user_id", "display_name"]:
            self.assertNotIn(private, content)


class RecommendationTests(ExtensionTestCase):
    def test_recommendations_prioritize_exact_preferences_then_time_and_hide_drafts(self):
        early = self.open_activity(title="推荐测试早场", theme="非偏好主题")
        preferred = self.open_activity(title="推荐测试偏好场", theme="测试偏好",
                                       start_time=(self.now + timedelta(hours=5)).isoformat(),
                                       end_time=(self.now + timedelta(hours=6)).isoformat())
        hidden = self.create_activity(title="推荐测试隐藏活动", theme="测试偏好")["id"]
        first = self.data(self.client("student").get("/api/recommendations?themes=测试偏好"))
        second = self.data(self.client("student").get("/api/recommendations?themes=测试偏好"))
        self.assertEqual(first, second)
        ids = [value["id"] for value in first]
        self.assertNotIn(hidden, ids)
        self.assertLess(ids.index(preferred), ids.index(early))
        self.assertTrue(all(value["recommendation_reason"] for value in first))
        unmatched = self.data(self.client("student").get("/api/recommendations?themes=测试偏"))
        expected = sorted(unmatched, key=lambda value: (value["start_time"], value["id"]))
        self.assertEqual([value["id"] for value in unmatched], [value["id"] for value in expected])

    def test_recommendations_without_preferences_use_public_activity_time_and_id(self):
        self.open_activity(title="排序同时间活动甲")
        self.open_activity(title="排序同时间活动乙")
        values = self.data(self.client("student").get("/api/recommendations"))
        public = self.data(self.app.test_client().get("/api/activities"))
        expected = sorted(public, key=lambda value: (value["start_time"], value["id"]))
        self.assertEqual([value["id"] for value in values], [value["id"] for value in expected])
        self.error(self.app.test_client().get("/api/recommendations"), 401)
        self.error(self.client("staff").get("/api/recommendations"), 403)


class ReportAndTodoTests(ExtensionTestCase):
    def test_reports_are_personal_until_staff_resolves_and_duplicates_are_rejected(self):
        activity_id = self.open_activity()
        endpoint = f"/api/activities/{activity_id}/reports"
        self.error(self.post("student", endpoint, {"reason": ""}), 400)
        report = self.data(self.post("student", endpoint, {"reason": "活动地点说明有误"}), 201)
        self.error(self.post("student", endpoint, {"reason": "活动地点说明有误"}), 409)
        self.assertEqual(self.data(self.client("member").get("/api/reports")), [])
        self.assertEqual(self.data(self.client("other_leader").get("/api/reports")), [])
        self.assertEqual([value["id"] for value in self.data(self.client("student").get("/api/reports"))], [report["id"]])
        self.assertTrue(any(value["id"] == report["id"] for value in self.data(self.client("staff").get("/api/reports"))))
        resolve = f"/api/reports/{report['id']}/resolve"
        self.error(self.post("leader", resolve, {"resolution": "已处理"}), 403)
        self.error(self.post("staff", resolve, {"resolution": ""}), 400)
        self.data(self.post("staff", resolve, {"resolution": "已核对并联系社团完善说明"}))
        own = self.data(self.client("student").get("/api/reports"))[0]
        self.assertEqual(own["status"], "resolved")
        self.assertEqual(own["resolution"], "已核对并联系社团完善说明")
        self.error(self.post("staff", resolve, {"resolution": "再次处理"}), 409)

    def test_reports_reject_hidden_activities_and_roll_back_failed_notifications(self):
        hidden = self.create_activity()["id"]
        self.error(self.post("student", f"/api/activities/{hidden}/reports", {"reason": "隐藏活动"}), 404)
        self.error(self.post("staff", "/api/activities/1/reports", {"reason": "测试"}), 403)
        with patch("campus_clubs.extensions.notify", side_effect=RuntimeError("private-report-diagnostic")):
            self.error(self.post("student", "/api/activities/1/reports", {"reason": "地点说明需要核对"}), 500)
        self.assertEqual(self.data(self.client("student").get("/api/reports")), [])
        self.data(self.post("student", "/api/activities/1/reports", {"reason": "地点说明需要核对"}), 201)

    def test_personal_todos_hide_other_clubs_and_completed_tasks_disappear(self):
        values = self.data(self.client("member").get("/api/todos"))
        task = next(value for value in values if value["kind"] == "task")
        self.assertTrue(task["title"])
        self.assertTrue(task["deadline"])
        self.assertFalse(any(value["kind"] == "task" and value["id"] == task["id"]
                             for value in self.data(self.client("other_leader").get("/api/todos"))))
        self.data(self.patch("member", f"/api/tasks/{task['id']}", {"status": "in_progress"}))
        self.data(self.patch("member", f"/api/tasks/{task['id']}", {"status": "done"}))
        self.assertFalse(any(value["kind"] == "task" and value["id"] == task["id"]
                             for value in self.data(self.client("member").get("/api/todos"))))

    def test_leader_and_staff_todos_include_only_their_actionable_pending_items(self):
        application = self.application()
        activity_id = self.submitted_activity()
        venue = self.data(self.venue_request(activity_id), 201)
        registration = self.data(self.post("student", "/api/club-registrations", {
            "name": "待办演示社团", "description": "待审核的社团备案。"}), 201)
        report = self.data(self.post("student", "/api/activities/1/reports", {"reason": "待核对信息"}), 201)
        leader_values = self.data(self.client("leader").get("/api/todos"))
        self.assertTrue(any(value["kind"] == "application" and value["id"] == application["id"] for value in leader_values))
        self.assertFalse(any(value["kind"] == "application" for value in self.data(self.client("other_leader").get("/api/todos"))))
        expected = {("activity", activity_id), ("venue_application", venue["id"]),
                    ("club_registration", registration["id"]), ("report", report["id"])}
        staff_values = self.data(self.client("staff").get("/api/todos"))
        self.assertTrue(expected.issubset({(value["kind"], value["id"]) for value in staff_values}))
        self.data(self.transition("staff", activity_id, "approve"))
        self.data(self.venue_review(venue["id"]))
        self.data(self.post("staff", f"/api/club-registrations/{registration['id']}/review", {"decision": "approve"}))
        self.data(self.post("staff", f"/api/reports/{report['id']}/resolve", {"resolution": "核对完成"}))
        self.data(self.post("leader", f"/api/applications/{application['id']}/review", {"decision": "approve"}))
        after = {(value["kind"], value["id"]) for value in self.data(self.client("staff").get("/api/todos"))}
        self.assertFalse(expected & after)
        self.assertFalse(any(value["kind"] == "application" and value["id"] == application["id"]
                             for value in self.data(self.client("leader").get("/api/todos"))))
