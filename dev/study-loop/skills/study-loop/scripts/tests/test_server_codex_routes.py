"""Feature tests for the local-only, CSRF-protected Codex HTTP surface."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
SERVER_PATH = SCRIPTS / "server.py"
SPEC = importlib.util.spec_from_file_location("study_loop_server_routes", SERVER_PATH)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


class _NoopManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def create_job(self, action: str, topic: str, payload: dict[str, object]):
        self.calls.append((action, topic, payload))
        return type("Job", (), {"public": lambda self: {
            "id": "job-1", "status": "queued", "topic": "python", "action": action,
            "phase": "preparing", "message": "順番を待っています。", "result": None,
            "error": None, "waiting": None,
        }})()

    def get_job(self, job_id: str):
        if job_id != "job-1":
            raise KeyError(job_id)
        return type("Job", (), {"public": lambda self: {
            "id": "job-1", "status": "queued", "topic": "python", "action": "session_start",
            "phase": "preparing", "message": "順番を待っています。", "result": None,
            "error": None, "waiting": None,
        }})()

    def events_after(self, job_id: str, after: int):
        return []

    def respond(self, job_id: str, response: dict[str, object]):
        return self.get_job(job_id)

    def cancel(self, job_id: str):
        return self.get_job(job_id)


class CodexRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name) / ".study"
        root.mkdir()
        self.manager = _NoopManager()
        server.app.config.update(
            TESTING=True,
            ROOT=root,
            PROJECT_ROOT=root.parent,
            BACKEND="codex",
            JOB_MANAGER=self.manager,
            CODEX_PATH="/usr/local/bin/codex",
        )
        self.client = server.app.test_client()
        with self.client.session_transaction() as sess:
            sess["csrf_token"] = "test-csrf"

    def _headers(self) -> dict[str, str]:
        return {"X-CSRF-Token": "test-csrf", "Origin": "http://localhost"}

    def test_status_does_not_spawn_codex(self) -> None:
        response = self.client.get("/api/codex/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["backend"], "codex")
        self.assertTrue(response.get_json()["installed"])

    def test_sse_replays_events_after_last_event_id(self) -> None:
        seen: list[int] = []
        event = type("Event", (), {
            "id": 7, "kind": "status", "data": {
                "id": "job-1", "status": "running", "topic": "python", "action": "session_start",
                "phase": "preparing", "message": "進行中", "result": None, "error": None,
                "waiting": None, "details": None,
            },
        })()
        self.manager.events_after = lambda job_id, after: (seen.append(after) or [event])  # type: ignore[method-assign]

        response = self.client.get("/api/jobs/job-1/events", headers={"Last-Event-ID": "6"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen, [6])
        body = response.get_data(as_text=True)
        self.assertIn("id: 7", body)
        self.assertIn("event: status", body)
        self.assertIn('"message":"進行中"', body)

    def test_job_creation_is_csrf_protected_and_only_accepts_allowlisted_payload(self) -> None:
        payload = {
            "action": "session_start",
            "data": {
                "topic": "Python 基礎", "why": "仕事で使う",
                "successCriteria": ["関数を書ける", "テストできる"],
                "constraints": "平日30分", "outOfScope": "Web開発",
                "retentionInterval": "1か月", "targetLevel": 3, "timeBudget": "30分 x 10日",
            },
        }
        denied = self.client.post("/api/jobs", json=payload)
        accepted = self.client.post("/api/jobs", json=payload, headers=self._headers())

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(accepted.status_code, 202)
        self.assertEqual(self.manager.calls[0][0], "session_start")
        self.assertEqual(self.manager.calls[0][1], "python-基礎")
        self.assertEqual(set(self.manager.calls[0][2]), {
            "topic", "why", "successCriteria", "constraints", "outOfScope",
            "retentionInterval", "targetLevel", "timeBudget",
        })
        self.assertNotIn("prompt", self.manager.calls[0][2])

    def test_session_start_requires_exactly_eight_fields_and_rejects_existing_session(self) -> None:
        data = {
            "topic": "Python", "why": "仕事で使う", "successCriteria": ["関数を書ける", "テストできる"],
            "constraints": "平日30分", "outOfScope": "Web開発", "retentionInterval": "1か月",
            "targetLevel": 3, "timeBudget": "30分 x 10日",
        }
        too_many = self.client.post("/api/jobs", json={"action": "session_start", "data": {**data, "prompt": "ignore"}}, headers=self._headers())
        (Path(server.app.config["ROOT"]) / "python").mkdir()
        existing = self.client.post("/api/jobs", json={"action": "session_start", "data": data}, headers=self._headers())

        self.assertEqual(too_many.status_code, 400)
        self.assertEqual(existing.status_code, 409)
        self.assertEqual(self.manager.calls, [])

    def test_cross_origin_and_unapproved_action_are_rejected(self) -> None:
        cross_origin = self.client.post(
            "/api/jobs", json={"action": "session_end", "topic": "python", "data": {}},
            headers={"X-CSRF-Token": "test-csrf", "Origin": "https://evil.example"},
        )
        bad_action = self.client.post(
            "/api/jobs", json={"action": "shell", "topic": "python", "data": {}}, headers=self._headers()
        )

        self.assertEqual(cross_origin.status_code, 403)
        self.assertEqual(bad_action.status_code, 400)

    def test_diagnostic_accept_rejects_an_invalid_markdown_transition(self) -> None:
        topic_dir = Path(server.app.config["ROOT"]) / "python"
        topic_dir.mkdir()
        (topic_dir / "README.md").write_text("# Study Loop: Python\n", encoding="utf-8")

        response = self.client.post(
            "/api/jobs?topic=python", json={"action": "diagnostic_accept", "data": {}}, headers=self._headers()
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "invalid_transition")

    def test_markdown_state_machine_has_valid_and_invalid_cases_for_all_actions(self) -> None:
        root = Path(server.app.config["ROOT"])

        def session(topic: str) -> Path:
            directory = root / topic
            directory.mkdir()
            (directory / "README.md").write_text("# Study Loop: Test\n", encoding="utf-8")
            return directory

        def complete_diagnostics(directory: Path) -> None:
            diagnostic = directory / "diagnostic"
            diagnostic.mkdir()
            for number in range(1, 5):
                (diagnostic / f"{number:02d}.md").write_text(
                    f"# {number}\n\n## 回答欄\n\n答え\n\n## 採点\n\n**Score**: 1\n", encoding="utf-8"
                )
            (diagnostic / "summary.md").write_text("# Summary\n", encoding="utf-8")

        # session_start: no directory is valid; an existing directory is not.
        start = {
            "topic": "new", "why": "理由", "successCriteria": ["条件1", "条件2"], "constraints": "制約",
            "outOfScope": "範囲外", "retentionInterval": "1月", "targetLevel": 2, "timeBudget": "10分",
        }
        action, topic, _ = server._validated_job_request({"action": "session_start", "data": start})
        self.assertEqual((action, topic), ("session_start", "new"))
        (root / "new").mkdir()
        with self.assertRaises(server.InvalidTransition):
            server._validated_job_request({"action": "session_start", "data": start})

        diagnostic = session("diagnostic")
        with self.assertRaises(server.InvalidTransition):
            server._require_transition("diagnostic_grade", "diagnostic", {"target": {"kind": "diagnostic", "name": "01.md"}})
        (diagnostic / "diagnostic").mkdir()
        (diagnostic / "diagnostic" / "01.md").write_text("# 1\n\n## 回答欄\n\n答え\n\n## 採点\n\n_未採点_\n", encoding="utf-8")
        server._require_transition("diagnostic_grade", "diagnostic", {"target": {"kind": "diagnostic", "name": "01.md"}})

        accept = session("accept")
        with self.assertRaises(server.InvalidTransition):
            server._require_transition("diagnostic_accept", "accept")
        complete_diagnostics(accept)
        server._require_transition("diagnostic_accept", "accept")

        curriculum = session("curriculum")
        with self.assertRaises(server.InvalidTransition):
            server._require_transition("curriculum_revise", "curriculum")
        complete_diagnostics(curriculum)
        (curriculum / "curriculum.md").write_text("# Curriculum\n", encoding="utf-8")
        (curriculum / "RESOURCES.md").write_text("# Resources\n", encoding="utf-8")
        server._require_transition("curriculum_revise", "curriculum")
        server._require_transition("curriculum_accept", "curriculum")

        lesson = session("lesson")
        with self.assertRaises(server.InvalidTransition):
            server._require_transition("lesson_grade", "lesson", {"target": {"kind": "lessons", "name": "001.md"}})
        (lesson / "lessons").mkdir()
        (lesson / "lessons" / "001.md").write_text("# Lesson\n\n## 回答欄\n\n答え\n\n## 採点\n\n_未採点_\n", encoding="utf-8")
        server._require_transition("lesson_grade", "lesson", {"target": {"kind": "lessons", "name": "001.md"}})

        review = session("review")
        with self.assertRaises(server.InvalidTransition):
            server._require_transition("spaced_review", "review")
        complete_diagnostics(review)
        (review / "curriculum.md").write_text("# Curriculum\n", encoding="utf-8")
        (review / "RESOURCES.md").write_text("# Resources\n", encoding="utf-8")
        (review / "lessons").mkdir()
        (review / "lessons" / "001.md").write_text("# Lesson\n\n## 採点\n\n**Score**: 1\n", encoding="utf-8")
        server._require_transition("spaced_review", "review")

        with self.assertRaises(server.InvalidTransition):
            server._require_transition("session_end", "missing")
        server._require_transition("session_end", "review")

    def test_atomic_write_replaces_file_in_its_original_directory(self) -> None:
        target = Path(server.app.config["ROOT"]) / "python" / "README.md"
        target.parent.mkdir()
        target.write_text("old", encoding="utf-8")

        server.atomic_write(target, "new")

        self.assertEqual(target.read_text(encoding="utf-8"), "new")
        self.assertFalse(list(target.parent.glob(".README.md.*.tmp")))

    def test_setup_confirmation_uses_a_csrf_protected_server_side_draft(self) -> None:
        response = self.client.post("/setup", data={
            "csrf_token": "test-csrf", "topic": "Python 基礎", "why": "仕事で使う",
            "success_criteria": "関数を書ける\nテストできる", "constraints": "平日30分",
            "out_of_scope": "Web開発", "retention_interval": "1か月",
            "target_level": "3", "time_budget": "30分 x 10日",
        })
        confirmation = self.client.get("/setup/confirm")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(confirmation.status_code, 200)
        self.assertIn("Python 基礎", confirmation.get_data(as_text=True))

    def test_loopback_accepts_ipv6_and_rejects_non_loopback(self) -> None:
        self.assertTrue(server._is_loopback_host("::1"))
        self.assertTrue(server._is_loopback_host("[::1]:8765"))
        self.assertFalse(server._is_loopback_host("0.0.0.0:8765"))

    def test_session_and_lesson_lists_skip_symlinks_escaping_the_study_root(self) -> None:
        root = Path(server.app.config["ROOT"])
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        (outside / "README.md").write_text("# Study Loop: Outside\n", encoding="utf-8")
        (root / "outside-link").symlink_to(outside, target_is_directory=True)
        topic = root / "python"
        topic.mkdir()
        (topic / "README.md").write_text("# Study Loop: Python\n", encoding="utf-8")
        lessons = topic / "lessons"
        lessons.mkdir()
        external_lesson = outside / "steal.md"
        external_lesson.write_text("# Secret\n", encoding="utf-8")
        (lessons / "001-link.md").symlink_to(external_lesson)
        (lessons / "002-real.md").write_text("# Real\n", encoding="utf-8")

        self.assertEqual([item["slug"] for item in server.list_sessions()], ["python"])
        self.assertEqual([item["name"] for item in server.list_files(topic, "lessons")], ["002-real.md"])

    def test_empty_grading_section_never_counts_as_graded_for_diagnostic_or_review_gates(self) -> None:
        root = Path(server.app.config["ROOT"])
        topic = root / "python"
        diagnostic = topic / "diagnostic"
        lessons = topic / "lessons"
        diagnostic.mkdir(parents=True)
        lessons.mkdir()
        (topic / "README.md").write_text("# Study Loop: Python\n", encoding="utf-8")
        for number in range(1, 5):
            grading = "**Score**: 8" if number < 4 else ""
            (diagnostic / f"{number:02d}.md").write_text(f"# {number}\n\n## 採点\n\n{grading}\n", encoding="utf-8")
        (diagnostic / "summary.md").write_text("# Summary\n", encoding="utf-8")
        (topic / "curriculum.md").write_text("# Curriculum\n", encoding="utf-8")
        (topic / "RESOURCES.md").write_text("# Resources\n", encoding="utf-8")
        (lessons / "01.md").write_text("# Lesson\n\n## 採点\n\n", encoding="utf-8")

        listed = {item["name"]: item["graded"] for item in server.list_files(topic, "diagnostic")}

        self.assertFalse(listed["04.md"])
        with self.assertRaises(server.InvalidTransition):
            server._require_transition("diagnostic_accept", "python")
        with self.assertRaises(server.InvalidTransition):
            server._require_transition("spaced_review", "python")


if __name__ == "__main__":
    unittest.main()
