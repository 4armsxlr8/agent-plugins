"""Regression tests for the App Server boundary and local UI hand-off."""

from __future__ import annotations

import importlib.util
import hashlib
import os
import shlex
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from contextlib import contextmanager
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from jobs import Job, JobManager, _validate_result  # type: ignore[import-not-found]
from codex_app_server import AppServerStatus, CodexAppServerClient  # type: ignore[import-not-found]
from protocol_fixture_validation import validate_jsonrpc_fixture  # type: ignore[import-not-found]


SERVER_PATH = SCRIPTS / "server.py"
SPEC = importlib.util.spec_from_file_location("study_loop_server_remediation", SERVER_PATH)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


class _IdleClient:
    crashed = False

    def close(self) -> None:
        return None


class _CaptureClient(_IdleClient):
    def __init__(self) -> None:
        self.replies: list[tuple[object, dict[str, object]]] = []
        self.errors: list[tuple[object, int, str]] = []
        self.interrupts: list[tuple[str, str]] = []

    def respond_to_server_request(self, request_id: object, result: dict[str, object]) -> None:
        self.replies.append((request_id, result))

    def respond_to_server_error(self, request_id: object, code: int, message: str) -> None:
        self.errors.append((request_id, code, message))

    def interrupt(self, *, thread_id: str, turn_id: str) -> None:
        self.interrupts.append((thread_id, turn_id))


class _BlockingClient(_CaptureClient):
    def set_handlers(self, *, on_notification, on_request) -> None:
        self.on_notification = on_notification
        self.on_request = on_request

    def connect(self, *, project_root: Path) -> AppServerStatus:
        return AppServerStatus(True, True, True, "利用可能")

    def start_turn(self, *, prompt: str, project_root: Path) -> tuple[str, str]:
        def ask() -> None:
            self.on_request({"id": "ask", "method": "item/tool/requestUserInput", "params": {
                "threadId": "thread", "turnId": "turn", "itemId": "item", "questions": [
                    {"id": "q", "header": "確認", "question": "続けますか？"},
                ],
            }})
        threading.Timer(0.01, ask).start()
        return "thread", "turn"

    def respond_to_server_request(self, request_id: object, result: dict[str, object]) -> None:
        super().respond_to_server_request(request_id, result)
        self.on_notification({"method": "item/agentMessage/delta", "params": {
            "threadId": "thread", "turnId": "turn", "itemId": "item", "delta": '{"status":"completed","summary":"完了","resultPath":null,"nextAction":"done"}',
        }})
        self.on_notification({"method": "turn/completed", "params": {
            "threadId": "thread", "turn": {"id": "turn", "status": "completed"},
        }})


class _ImmediateRequestClient(_BlockingClient):
    def start_turn(self, *, prompt: str, project_root: Path) -> tuple[str, str]:
        self.on_request({"id": "immediate", "method": "item/tool/requestUserInput", "params": {
            "threadId": "thread", "turnId": "turn", "itemId": "item", "questions": [
                {"id": "q", "header": "確認", "question": "続けますか？"},
            ],
        }})
        return "thread", "turn"


class _RevisionClient(_CaptureClient):
    def __init__(self) -> None:
        super().__init__()
        self.start_calls = 0

    def set_handlers(self, *, on_notification, on_request) -> None:
        self.on_notification = on_notification
        self.on_request = on_request

    def connect(self, *, project_root: Path) -> AppServerStatus:
        return AppServerStatus(True, True, True, "利用可能")

    def start_turn(self, *, prompt: str, project_root: Path) -> tuple[str, str]:
        self.start_calls += 1
        def complete() -> None:
            self.on_notification({"method": "item/agentMessage/delta", "params": {
                "threadId": "thread", "turnId": "turn", "itemId": "item", "delta": '{"status":"completed","summary":"完了","resultPath":null,"nextAction":"done"}',
            }})
            self.on_notification({"method": "turn/completed", "params": {
                "threadId": "thread", "turn": {"id": "turn", "status": "completed"},
            }})
        threading.Timer(0.01, complete).start()
        return "thread", "turn"


class _ApplyPatchFlowClient(_CaptureClient):
    """Fixture: Codex changes Markdown only after its file-change approval."""

    def set_handlers(self, *, on_notification, on_request) -> None:
        self.on_notification = on_notification
        self.on_request = on_request

    def connect(self, *, project_root: Path) -> AppServerStatus:
        return AppServerStatus(True, True, True, "利用可能")

    def start_turn(self, *, prompt: str, project_root: Path) -> tuple[str, str]:
        self.project_root = project_root
        threading.Timer(0.01, lambda: self.on_request({"id": "apply-launcher", "method": "item/commandExecution/requestApproval", "params": {
            "threadId": "thread", "turnId": "turn", "itemId": "item",
            "command": "/bin/zsh -c apply_patch", "cwd": str(project_root),
            "reason": "Markdown を更新するための Codex 標準ランチャー", "startedAtMs": 1,
            "commandActions": [{"type": "unknown", "command": "apply_patch"}],
            "availableDecisions": ["accept", "decline", "cancel"],
        }})).start()
        return "thread", "turn"

    def respond_to_server_request(self, request_id: object, result: dict[str, object]) -> None:
        super().respond_to_server_request(request_id, result)
        if request_id == "apply-launcher" and result == {"decision": "accept"}:
            self.on_request({"id": "file-change", "method": "item/fileChange/requestApproval", "params": {
                "threadId": "thread", "turnId": "turn", "itemId": "item",
                "cwd": str(self.project_root), "grantRoot": str(self.project_root / ".study"),
                "reason": "採点結果を Markdown に保存", "startedAtMs": 2,
            }})
        elif request_id == "file-change" and result == {"decision": "accept"}:
            target = self.project_root / ".study" / "python" / "diagnostic" / "01.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# Diagnostic\n\n## 採点\n\n**Score**: 8\n", encoding="utf-8")
            self.on_notification({"method": "item/agentMessage/delta", "params": {
                "threadId": "thread", "turnId": "turn", "itemId": "item",
                "delta": '{"status":"completed","summary":"採点を保存","resultPath":".study/python/diagnostic/01.md","nextAction":"answer"}',
            }})
            self.on_notification({"method": "turn/completed", "params": {
                "threadId": "thread", "turn": {"id": "turn", "status": "completed"},
            }})


class _TerminalLessClient(_CaptureClient):
    """A turn that never sends a terminal notification unless force-stopped."""

    def __init__(self) -> None:
        super().__init__()
        self.terminated = threading.Event()

    def set_handlers(self, *, on_notification, on_request) -> None:
        self.on_notification = on_notification
        self.on_request = on_request

    def connect(self, *, project_root: Path) -> AppServerStatus:
        return AppServerStatus(True, True, True, "利用可能")

    def start_turn(self, *, prompt: str, project_root: Path) -> tuple[str, str]:
        return "terminal-less-thread", "terminal-less-turn"

    def terminate_for_cancel(self) -> bool:
        self.terminated.set()
        return True


class _LateExitClient(_TerminalLessClient):
    """The first termination attempt races a process that exits shortly after."""

    def __init__(self) -> None:
        super().__init__()
        self.termination_attempts = 0

    def terminate_for_cancel(self) -> bool:
        self.termination_attempts += 1
        return self.termination_attempts >= 2


class _SlowInterruptClient(_CaptureClient):
    def __init__(self) -> None:
        super().__init__()
        self.interrupt_started = threading.Event()
        self.release_interrupt = threading.Event()

    def interrupt(self, *, thread_id: str, turn_id: str) -> None:
        self.interrupts.append((thread_id, turn_id))
        self.interrupt_started.set()
        self.release_interrupt.wait(1)


class _CancelDuringStartClient(_TerminalLessClient):
    def __init__(self) -> None:
        super().__init__()
        self.start_entered = threading.Event()
        self.allow_return = threading.Event()
        self.cancel_callback = None

    def start_turn(self, *, prompt: str, project_root: Path) -> tuple[str, str]:
        self.start_entered.set()
        self.allow_return.wait(1)
        assert self.cancel_callback is not None
        self.cancel_callback()
        return "terminal-less-thread", "terminal-less-turn"


class _ControlledStartClient(_TerminalLessClient):
    def __init__(self) -> None:
        super().__init__()
        self.start_entered = threading.Event()
        self.allow_return = threading.Event()

    def start_turn(self, *, prompt: str, project_root: Path) -> tuple[str, str]:
        self.start_entered.set()
        self.allow_return.wait(1)
        return "terminal-less-thread", "terminal-less-turn"


class _CompletingClient(_TerminalLessClient):
    def start_turn(self, *, prompt: str, project_root: Path) -> tuple[str, str]:
        def complete() -> None:
            self.on_notification({"method": "item/agentMessage/delta", "params": {
                "threadId": "complete-thread", "turnId": "complete-turn", "itemId": "item",
                "delta": '{"status":"completed","summary":"完了","resultPath":null,"nextAction":"done"}',
            }})
            self.on_notification({"method": "turn/completed", "params": {
                "threadId": "complete-thread", "turn": {"id": "complete-turn", "status": "completed"},
            }})
        threading.Timer(0.01, complete).start()
        return "complete-thread", "complete-turn"


class _NoStartClient(_CaptureClient):
    def __init__(self) -> None:
        super().__init__()
        self.start_calls = 0

    def set_handlers(self, *, on_notification, on_request) -> None:
        self.on_notification = on_notification
        self.on_request = on_request

    def connect(self, *, project_root: Path) -> AppServerStatus:
        return AppServerStatus(True, True, True, "利用可能")

    def start_turn(self, *, prompt: str, project_root: Path) -> tuple[str, str]:
        self.start_calls += 1
        return "thread", "turn"


class _ResultClient(_NoStartClient):
    def start_turn(self, *, prompt: str, project_root: Path) -> tuple[str, str]:
        self.start_calls += 1
        def complete() -> None:
            self.on_notification({"method": "item/agentMessage/delta", "params": {
                "threadId": "result-thread", "turnId": "result-turn", "itemId": "item",
                "delta": '{"status":"completed","summary":"完了","resultPath":null,"nextAction":"done"}',
            }})
            self.on_notification({"method": "turn/completed", "params": {
                "threadId": "result-thread", "turn": {"id": "result-turn", "status": "completed"},
            }})
        threading.Timer(0.01, complete).start()
        return "result-thread", "result-turn"


class _RouteManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def create_job(self, action: str, topic: str, payload: dict[str, object]):
        self.calls.append((action, topic, payload))
        return type("Job", (), {"public": lambda self: {
            "id": "job-1", "status": "queued", "topic": topic, "action": action,
            "phase": "preparing", "message": "順番を待っています。", "result": None,
            "error": None, "waiting": None, "details": None,
        }})()

    def get_job(self, job_id: str):
        if job_id != "job-1":
            raise KeyError(job_id)
        return self.create_job("session_start", "python", {})

    def events_after(self, job_id: str, after: int):
        return []

    def respond(self, job_id: str, response: dict[str, object]):
        return self.get_job(job_id)

    def cancel(self, job_id: str):
        return self.get_job(job_id)


class _CompletedLessonManager(_RouteManager):
    def __init__(self) -> None:
        super().__init__()
        self.consumed = False
        self.reserved = False

    def get_job(self, job_id: str):
        if job_id != "lesson-source":
            raise KeyError(job_id)
        return type("Job", (), {
            "status": "completed",
            "action": "lesson_grade",
            "topic": "python",
            "payload": {
                "target": {"kind": "lessons", "name": "03-functions.md"},
                "feedback": {"tags": ["境界値"], "note": "式を確認"},
            },
            "result": {"status": "completed", "summary": "採点済み", "resultPath": None, "nextAction": "retry_or_continue"},
        })()

    def reserve_lesson_resolution(self, job_id: str):
        if self.reserved or self.consumed:
            raise ValueError("already used")
        self.reserved = True
        return self.get_job(job_id)

    def release_lesson_resolution(self, job_id: str) -> None:
        if not self.consumed:
            self.reserved = False

    def commit_lesson_resolution(self, job_id: str) -> None:
        if not self.reserved or self.consumed:
            raise ValueError("already used")
        self.reserved = False
        self.consumed = True


class _ReservationRouteManager(_CompletedLessonManager):
    def __init__(self) -> None:
        super().__init__()
        self.reserved = False
        self.fail_create = True

    def create_job(self, action: str, topic: str, payload: dict[str, object]):
        if self.fail_create:
            raise ValueError("このトピックでは、すでに Codex の処理が進行中です。")
        return super().create_job(action, topic, payload)


class PermissionBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.manager = JobManager(project_root=self.root, client_factory=_IdleClient)
        self.addCleanup(self.manager.close)

    def test_legacy_read_write_paths_and_symlink_escape_are_auto_denied(self) -> None:
        outside = Path(self.tmp.name).parent / "study-outside"
        outside.mkdir(exist_ok=True)
        escaped_link = self.root / "escaped"
        escaped_link.symlink_to(outside, target_is_directory=True)
        params = {
            "cwd": str(self.root),
            "permissions": {
                "fileSystem": {
                    "read": [str(outside)],
                    "write": [str(escaped_link / "answer.md")],
                    "entries": [{"access": "read", "path": {"type": "glob_pattern", "pattern": str(outside / "**")}}],
                },
            },
        }

        self.assertTrue(self.manager._has_external_request(params))
        self.assertEqual(self.manager._safe_permission_subset(params["permissions"]), {})
        glob_only = {
            "cwd": str(self.root),
            "permissions": {"fileSystem": {"entries": [
                {"access": "read", "path": {"type": "glob_pattern", "pattern": str(outside / "**")}},
            ]}},
        }
        self.assertTrue(self.manager._has_external_request(glob_only))


class ResultPathValidationTests(unittest.TestCase):
    def test_result_path_must_be_an_existing_regular_file_for_the_same_topic_and_action(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        diagnostic = root / ".study" / "python" / "diagnostic" / "01-start.md"
        diagnostic.parent.mkdir(parents=True)
        diagnostic.write_text("# 診断", encoding="utf-8")
        other = root / ".study" / "other" / "diagnostic" / "01-other.md"
        other.parent.mkdir(parents=True)
        other.write_text("# Other", encoding="utf-8")
        wrong_kind = root / ".study" / "python" / "lessons" / "01-start.md"
        wrong_kind.parent.mkdir(parents=True)
        wrong_kind.write_text("# Lesson", encoding="utf-8")
        symlink = root / ".study" / "python" / "diagnostic" / "02-link.md"
        symlink.symlink_to(other)
        result = {"status": "completed", "summary": "完了", "resultPath": ".study/python/diagnostic/01-start.md", "nextAction": "answer"}

        self.assertEqual(_validate_result(result, root, "python", "session_start")["resultPath"], result["resultPath"])
        for bad in [
            {**result, "resultPath": ".study/python/diagnostic/missing.md"},
            {**result, "resultPath": ".study/other/diagnostic/01-other.md"},
            {**result, "resultPath": ".study/python/diagnostic/02-link.md"},
            {**result, "resultPath": ".study/python/lessons/01-start.md"},
        ]:
            with self.assertRaises(ValueError):
                _validate_result(bad, root, "python", "session_start")

    def test_result_path_rejects_a_symlinked_topic_or_intermediate_directory(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        external_topic = root / "external" / "python"
        external_diagnostic = external_topic / "diagnostic"
        external_diagnostic.mkdir(parents=True)
        (external_diagnostic / "01.md").write_text("# External\n", encoding="utf-8")
        study = root / ".study"
        study.mkdir()
        (study / "python").symlink_to(external_topic, target_is_directory=True)
        result = {"status": "completed", "summary": "完了", "resultPath": ".study/python/diagnostic/01.md", "nextAction": "answer"}

        with self.assertRaises(ValueError):
            _validate_result(result, root, "python", "session_start")

        (study / "python").unlink()
        topic = study / "python"
        topic.mkdir()
        (topic / "diagnostic").symlink_to(external_diagnostic, target_is_directory=True)
        with self.assertRaises(ValueError):
            _validate_result(result, root, "python", "session_start")


class CodexLauncherTests(unittest.TestCase):
    def test_apply_patch_launcher_must_be_exact_codex_arg0_link_to_a_trusted_binary(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        codex_home = root / ".codex"
        launcher_dir = codex_home / "tmp" / "arg0" / "codex-arg0AbC123"
        launcher_dir.mkdir(parents=True)
        codex = root / "Codex.app" / "Contents" / "Resources" / "codex"
        codex.parent.mkdir(parents=True)
        codex.write_text("#!/bin/sh\n", encoding="utf-8")
        codex.chmod(0o755)
        launcher = launcher_dir / "apply_patch"
        launcher.symlink_to(codex)

        resolved = CodexAppServerClient._resolve_apply_patch_launcher(
            path_env=str(launcher_dir), codex_home=codex_home, trusted_binaries={codex.resolve()},
        )
        self.assertEqual(resolved, launcher)

        untrusted = root / "untrusted-codex"
        untrusted.write_text("#!/bin/sh\n", encoding="utf-8")
        untrusted.chmod(0o755)
        launcher.unlink()
        launcher.symlink_to(untrusted)
        self.assertIsNone(CodexAppServerClient._resolve_apply_patch_launcher(
            path_env=str(launcher_dir), codex_home=codex_home, trusted_binaries={codex.resolve()},
        ))

        project_launcher_dir = root / "project" / "apply"
        project_launcher_dir.mkdir(parents=True)
        project_launcher = project_launcher_dir / "apply_patch"
        project_launcher.symlink_to(codex)
        self.assertIsNone(CodexAppServerClient._resolve_apply_patch_launcher(
            path_env=str(project_launcher_dir), codex_home=codex_home, trusted_binaries={codex.resolve()},
        ))

    def test_thread_config_adds_only_a_verified_apply_patch_parent(self) -> None:
        client = CodexAppServerClient(study_loop_skill_root=SCRIPTS.parent)
        safe = Path("/private/tmp/codex-arg0-safe/apply_patch")
        original = client._resolve_apply_patch_launcher
        client._resolve_apply_patch_launcher = lambda **_kwargs: safe  # type: ignore[method-assign]
        self.addCleanup(setattr, client, "_resolve_apply_patch_launcher", original)
        safe_path = client._thread_config_override()["shell_environment_policy"]["set"]["PATH"]
        self.assertIn(str(safe.parent), safe_path.split(os.pathsep))

        client._resolve_apply_patch_launcher = lambda **_kwargs: None  # type: ignore[method-assign]
        unavailable_path = client._thread_config_override()["shell_environment_policy"]["set"]["PATH"]
        self.assertNotIn(str(safe.parent), unavailable_path.split(os.pathsep))


class FrontendSecurityContractTests(unittest.TestCase):
    def test_mermaid_theme_rerender_restores_source_as_text_in_strict_mode(self) -> None:
        ui = (SCRIPTS / "static" / "app.js").read_text(encoding="utf-8")

        self.assertIn("securityLevel: \"strict\"", ui)
        self.assertIn("el.textContent = el.dataset.source || el.textContent;", ui)
        self.assertNotIn("el.innerHTML = el.dataset.source", ui)


class ServerRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.capture = _CaptureClient()
        self.manager = JobManager(project_root=self.root, client_factory=lambda: self.capture)
        self.addCleanup(self.manager.close)
        self.manager._client = self.capture
        self.job = Job("job", "lesson_grade", "python", {"target": {"kind": "lessons", "name": "01.md"}})
        self.job.status = "running"
        self.job.thread_id = "thread-1"
        self.job.turn_id = "turn-1"
        self.manager._jobs[self.job.id] = self.job
        self.manager._active_id = self.job.id

    def _params(self, **extra: object) -> dict[str, object]:
        return {"threadId": "thread-1", "turnId": "turn-1", "itemId": "item-1", **extra}

    def test_questions_are_correlated_and_secret_answers_never_enter_public_event_data(self) -> None:
        self.manager._on_request({"id": "request-1", "method": "item/tool/requestUserInput", "params": self._params(questions=[
            {"id": "secret", "header": "認証", "question": "キー", "isSecret": True},
            {"id": "style", "header": "形式", "question": "選んでください", "isOther": True, "options": [{"label": "短く", "description": "要点だけ"}]},
        ])})

        self.assertEqual(self.job.status, "waiting_input")
        self.assertTrue(self.job.public()["details"]["questions"][0]["isSecret"])
        self.assertNotIn("secret-value", repr(self.job.events))
        returned = self.manager.respond("job", {"answers": {"secret": ["secret-value"], "style": ["自由入力"]}})

        self.assertEqual(returned.status, "running")
        self.assertEqual(self.capture.replies[-1], ("request-1", {"answers": {"secret": {"answers": ["secret-value"]}, "style": {"answers": ["自由入力"]}}}))
        ui = (SCRIPTS / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("document.createElement(question.isSecret ? 'input' : 'textarea')", ui)
        self.assertIn("field.type = 'password'", ui)
        self.assertIn("other.value = '__other__'", ui)
        self.assertIn("otherText.required = choosingOther", ui)
        self.assertIn("field.value === '__other__' ? other?.value : field.value", ui)
        self.assertIn("if (!useOther && other) other.value = '';", ui)
        self.assertNotIn("other?.value || field.value", ui)

    def test_response_for_a_failed_old_job_cannot_reach_a_restarted_client(self) -> None:
        old = Job("old", "lesson_grade", "python", {})
        old.status = "waiting_input"
        old.thread_id = "old-thread"
        old.turn_id = "old-turn"
        old.pending_request_id = "old-request"
        old.pending_kind = "input"
        old.pending_details = {"questions": [{"id": "q"}]}
        self.manager._jobs[old.id] = old
        restarted_client = _CaptureClient()
        self.manager._client = restarted_client

        with self.assertRaises(ValueError):
            self.manager.respond(old.id, {"answers": {"q": ["stale"]}})

        self.assertEqual(restarted_client.replies, [])
        self.assertEqual(old.pending_request_id, "old-request")

    def test_cancel_for_a_non_active_old_job_cannot_interrupt_a_restarted_client(self) -> None:
        old = Job("old", "lesson_grade", "python", {})
        old.status = "running"
        old.thread_id = "old-thread"
        old.turn_id = "old-turn"
        self.manager._jobs[old.id] = old
        restarted_client = _CaptureClient()
        self.manager._client = restarted_client

        with self.assertRaises(ValueError):
            self.manager.cancel(old.id)

        self.assertEqual(restarted_client.interrupts, [])

    def test_failed_terminal_transition_clears_pending_browser_request(self) -> None:
        self.job.status = "waiting_input"
        self.job.pending_request_id = "request-1"
        self.job.pending_kind = "input"
        self.job.pending_details = {"questions": [{"id": "q"}]}

        self.manager._on_notification({"method": "turn/completed", "params": {
            "threadId": "thread-1", "turn": {"id": "turn-1", "status": "failed"},
        }})

        self.assertEqual(self.job.status, "failed")
        self.assertIsNone(self.job.pending_request_id)
        self.assertIsNone(self.job.pending_kind)
        self.assertIsNone(self.job.pending_details)

    def test_notification_from_replaced_client_generation_cannot_finish_current_job(self) -> None:
        old_client = _CaptureClient()
        new_client = _CaptureClient()
        self.manager._client = new_client
        self.manager._client_generation = 2
        self.job.status = "running"

        self.manager._on_notification(
            {"method": "turn/completed", "params": {
                "threadId": "thread-1", "turn": {"id": "turn-1", "status": "failed"},
            }},
            source_client=old_client,
            source_generation=1,
        )

        self.assertEqual(self.job.status, "running")
        self.assertFalse(self.job.done.is_set())

    def test_notification_callback_does_not_block_on_interrupt_response(self) -> None:
        slow = _SlowInterruptClient()
        self.manager._client = slow
        started = time.monotonic()
        self.manager._on_notification({"method": "item/started", "params": {
            "threadId": "thread-1", "turnId": "turn-1", "item": {"type": "mcpToolCall"},
        }})
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 0.1)
        self.assertTrue(slow.interrupt_started.wait(0.2))
        self.manager._on_notification({"method": "turn/completed", "params": {
            "threadId": "thread-1", "turn": {"id": "turn-1", "status": "interrupted"},
        }})
        self.assertEqual(self.job.status, "failed")
        slow.release_interrupt.set()

    def test_repeated_cancel_sends_one_interrupt_for_the_same_turn(self) -> None:
        self.manager.cancel(self.job.id)
        self.manager.cancel(self.job.id)
        deadline = time.monotonic() + 0.2
        while len(self.capture.interrupts) < 1 and time.monotonic() < deadline:
            time.sleep(0.005)

        self.assertEqual(self.capture.interrupts, [("thread-1", "turn-1")])

    def test_repeated_forbidden_integration_notification_sends_one_interrupt_for_the_same_turn(self) -> None:
        notification = {"method": "item/started", "params": {
            "threadId": "thread-1", "turnId": "turn-1", "item": {"type": "mcpToolCall"},
        }}
        self.manager._on_notification(notification)
        self.manager._on_notification(notification)
        deadline = time.monotonic() + 0.2
        while len(self.capture.interrupts) < 1 and time.monotonic() < deadline:
            time.sleep(0.005)

        self.assertEqual(self.capture.interrupts, [("thread-1", "turn-1")])

    def test_approval_responses_are_exact_and_external_paths_are_denied(self) -> None:
        self.manager._on_request({"id": 7, "method": "item/commandExecution/requestApproval", "params": self._params(
            command="pwd", cwd=str(self.root), reason="作業場所の確認", startedAtMs=1,
            availableDecisions=["accept", "decline", "cancel"],
        )})
        with self.assertRaises(ValueError):
            self.manager.respond("job", {"decision": "accept", "keep": "forever"})
        self.manager.respond("job", {"decision": "accept"})
        self.assertEqual(self.capture.replies[-1], (7, {"decision": "accept"}))

        outside = str(self.root.parent / "outside")
        self.manager._on_request({"id": "external", "method": "item/permissions/requestApproval", "params": self._params(
            cwd=str(self.root), permissions={"fileSystem": {"read": [outside]}}, startedAtMs=1,
        )})
        self.assertEqual(self.capture.replies[-1], ("external", {"permissions": {}, "scope": "turn"}))

    def test_full_command_and_additional_permissions_are_checked_before_any_acceptance(self) -> None:
        outside = str(self.root.parent / "outside")
        command = "printf safe " + ("x" * 300) + f" > {outside}/answer.md"
        self.manager._on_request({"id": "long-external", "method": "item/commandExecution/requestApproval", "params": self._params(
            command=command, cwd=str(self.root), reason="保存", startedAtMs=1,
            additionalPermissions={"fileSystem": {"write": [outside]}},
            availableDecisions=["accept", "decline", "cancel", "acceptForSession"],
        )})

        self.assertEqual(self.capture.replies[-1], ("long-external", {"decision": "decline"}))
        self.assertEqual(self.job.status, "running")

        local_command = "printf ok > answer.md"
        self.manager._on_request({"id": "limited", "method": "item/commandExecution/requestApproval", "params": self._params(
            command=local_command, cwd=str(self.root), reason="保存", startedAtMs=1,
            additionalPermissions={"fileSystem": {"write": [str(self.root / "answer.md")] }},
            availableDecisions=["decline", "cancel"],
        )})
        self.assertEqual(self.capture.replies[-1], ("limited", {"decision": "decline"}))
        self.assertEqual(self.job.status, "running")

    def test_redirects_and_assignment_path_operands_are_auto_denied(self) -> None:
        """Browser approval never permits shell redirection or hidden absolute paths."""
        for request_id, command in enumerate([
            "printf ok > answer.md",
            "dd if=/dev/zero of=/tmp/escaped",
        ]):
            self.manager._on_request({"id": f"redirect-or-assignment-{request_id}", "method": "item/commandExecution/requestApproval", "params": self._params(
                command=command, cwd=str(self.root), reason="実行", startedAtMs=1,
                availableDecisions=["accept", "decline", "cancel"],
            )})
            self.assertEqual(self.job.status, "running", command)
            self.assertEqual(
                self.capture.replies[-1],
                (f"redirect-or-assignment-{request_id}", {"decision": "decline"}),
                command,
            )

    def test_only_fixed_shell_wrapper_and_allowlisted_executables_reach_approval(self) -> None:
        """Dispatchers and interactive shells cannot turn an approval into arbitrary code."""
        for request_id, command in enumerate([
            "make lesson",
            "ninja lesson",
            "npm run lesson",
            "python lesson.py",
            "/bin/zsh -ic pwd",
            "/bin/zsh -l -c pwd",
        ]):
            self.manager._on_request({"id": f"unallowlisted-{request_id}", "method": "item/commandExecution/requestApproval", "params": self._params(
                command=command, cwd=str(self.root), reason="実行", startedAtMs=1,
                availableDecisions=["accept", "decline", "cancel"],
            )})
            self.assertEqual(self.job.status, "running", command)
            self.assertEqual(self.capture.replies[-1], (f"unallowlisted-{request_id}", {"decision": "decline"}), command)

    def test_command_approval_permits_only_bounded_read_commands(self) -> None:
        """Read approvals have a small, parsed grammar with local targets only."""
        bundled_skill = (SCRIPTS.parent / "SKILL.md").resolve()
        bundled_reference = (SCRIPTS.parent / "references" / "rubric.md").resolve()
        for request_id, command in enumerate([
            "pwd",
            "ls -la",
            "ls -lah .",
            "git status --short -- lessons",
            "rg --files lessons .study",
            "sed -n 1,80p lessons/01.md",
            "cat lessons/01.md",
            f"sed -n 1,80p {bundled_skill}",
            f"cat {bundled_skill}",
            f"sed -n 1,80p {bundled_reference}",
            f"cat {bundled_reference}",
            "/bin/zsh -c 'ls -la .',",
            "/bin/zsh -c 'sed -n 1,80p lessons/01.md'",
            "/bin/zsh -c 'rg --files lessons .study'",
        ]):
            self.manager._on_request({"id": f"safe-read-{request_id}", "method": "item/commandExecution/requestApproval", "params": self._params(
                command=command, cwd=str(self.root), reason="内容の確認", startedAtMs=1,
                availableDecisions=["accept", "decline", "cancel"],
            )})
            self.assertEqual(self.job.status, "waiting_approval", command)
            self.manager.respond("job", {"decision": "decline"})

    def test_sha256_integrity_check_is_limited_to_one_existing_local_file(self) -> None:
        """The sole integrity exception cannot become a general command runner."""
        lesson = self.root / "lesson.md"
        lesson.write_text("answer", encoding="utf-8")
        safe = "/bin/zsh -c 'shasum -a 256 lesson.md'"
        safe_actions = [{"type": "unknown", "command": "shasum -a 256 lesson.md"}]
        self.manager._on_request({"id": "safe-sha", "method": "item/commandExecution/requestApproval", "params": self._params(
            command=safe, cwd=str(self.root), reason="回答が送信後に変わっていないかを確認", startedAtMs=1,
            commandActions=safe_actions, availableDecisions=["accept", "decline", "cancel"],
        )})
        self.assertEqual(self.job.status, "waiting_approval")
        self.manager.respond("job", {"decision": "decline"})

        escaped = self.root.parent / "outside.md"
        escaped.write_text("outside", encoding="utf-8")
        escaped_link = self.root / "escaped.md"
        escaped_link.symlink_to(escaped)
        fake = self.root / "shasum"
        fake.write_text("not a digest tool", encoding="utf-8")
        fake.chmod(0o755)
        rejected = [
            "shasum lesson.md",
            "shasum -a 1 lesson.md",
            "shasum -a 256 lesson.md another.md",
            "shasum -a 256 missing.md",
            "shasum -a 256 ../outside.md",
            "shasum -a 256 escaped.md",
            "/tmp/shasum -a 256 lesson.md",
            f"{fake} -a 256 lesson.md",
            "shasum -a 256 lesson.md; pwd",
        ]
        for number, command in enumerate(rejected):
            self.manager._on_request({"id": f"unsafe-sha-{number}", "method": "item/commandExecution/requestApproval", "params": self._params(
                command=command, cwd=str(self.root), reason="確認", startedAtMs=1,
                commandActions=[{"type": "unknown", "command": command}], availableDecisions=["accept", "decline", "cancel"],
            )})
            self.assertEqual(self.capture.replies[-1], (f"unsafe-sha-{number}", {"decision": "decline"}), command)

        for action in [
            [{"type": "unknown", "command": "shasum -a 256 another.md"}],
            [{"type": "unknown", "command": "shasum -a 256 lesson.md", "path": "lesson.md"}],
        ]:
            self.manager._on_request({"id": "mismatched-sha-action", "method": "item/commandExecution/requestApproval", "params": self._params(
                command=safe, cwd=str(self.root), reason="確認", startedAtMs=1,
                commandActions=action, availableDecisions=["accept", "decline", "cancel"],
            )})
            self.assertEqual(self.capture.replies[-1], ("mismatched-sha-action", {"decision": "decline"}))

        self.assertIn("直前に SHA-256 を再検証済み", self.manager._prompt_for(self.job))

    def test_command_approval_rejects_skill_root_symlink_and_parent_escape(self) -> None:
        """Bundled reads must resolve to an existing regular file inside the skill root."""
        skill_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(skill_tmp.cleanup)
        skill_root = Path(skill_tmp.name) / "study-loop-skill"
        references = skill_root / "references"
        references.mkdir(parents=True)
        self.manager._bundled_skill_root = lambda: skill_root  # type: ignore[method-assign]
        escaped_target = skill_root.parent / "outside.md"
        escaped_target.write_text("outside", encoding="utf-8")
        escaped_link = references / "approval-escape-test.md"
        escaped_link.symlink_to(escaped_target)
        for path in [str(escaped_link), str(skill_root / ".." / "outside.md")]:
            self.assertFalse(self.manager._read_path_is_approval_safe(path, self.root), path)

    def test_command_approval_rejects_unbounded_or_nonlocal_read_commands(self) -> None:
        """Options, expression languages, and paths outside the two read roots are denied."""
        for request_id, command in enumerate([
            "rg --pre pwd needle",
            "rg --files",
            "rg --files --pre pwd",
            "rg --files --glob '*.md' lessons",
            "rg --files ../",
            "rg --files /tmp",
            "rg --files lessons | cat",
            "./rg --files lessons",
            "./rg needle",
            "sed -n 's/x/y/e' lesson.md",
            "ls -R",
            "ls -la ../",
            "git status --short",
            "git status --short -- ../",
            "sed -n 1,80p ../lesson.md",
            "cat ../lesson.md",
            "pwd -P",
            "/bin/zsh -lc 'pwd -P'",
            "/bin/zsh -lc 'ls -la . | cat'",
        ]):
            self.manager._on_request({"id": f"not-exact-pwd-{request_id}", "method": "item/commandExecution/requestApproval", "params": self._params(
                command=command, cwd=str(self.root), reason="実行", startedAtMs=1,
                availableDecisions=["accept", "decline", "cancel"],
            )})
            self.assertEqual(
                self.capture.replies[-1],
                (f"not-exact-pwd-{request_id}", {"decision": "decline"}),
                command,
            )
            self.assertEqual(self.job.status, "running", command)

    def test_rg_files_rejects_a_project_symlink_that_escapes(self) -> None:
        escaped_link = self.root / "escaped-link"
        escaped_link.symlink_to(self.root.parent / "outside")
        self.manager._on_request({"id": "rg-symlink", "method": "item/commandExecution/requestApproval", "params": self._params(
            command="rg --files escaped-link", cwd=str(self.root), reason="内容の確認", startedAtMs=1,
            availableDecisions=["accept", "decline", "cancel"],
        )})
        self.assertEqual(self.capture.replies[-1], ("rg-symlink", {"decision": "decline"}))
        self.assertEqual(self.job.status, "running")

    def test_relative_command_paths_are_checked_from_cwd_and_structured_choices_are_ignored(self) -> None:
        outside = self.root.parent / "escaped.md"
        for request_id, command in enumerate([
            "touch ../escaped.md",
            "printf safe > ../escaped.md",
            "printf safe > '../escaped.md'",
            f"touch {outside}",
        ], start=1):
            self.manager._on_request({"id": request_id, "method": "item/commandExecution/requestApproval", "params": self._params(
                command=command, cwd=str(self.root), reason="保存", startedAtMs=1,
                availableDecisions=["accept", "decline", "cancel"],
            )})
            self.assertEqual(self.capture.replies[-1], (request_id, {"decision": "decline"}))
            self.assertEqual(self.job.status, "running")

        self.manager._on_request({"id": "command-actions", "method": "item/commandExecution/requestApproval", "params": self._params(
            command="touch lesson.md", cwd=str(self.root), reason="保存", startedAtMs=1,
            commandActions=[{"type": "write", "path": "../escaped.md"}],
            availableDecisions=["accept", "decline", "cancel"],
        )})
        self.assertEqual(self.capture.replies[-1], ("command-actions", {"decision": "decline"}))

        self.manager._on_request({"id": "benign", "method": "item/commandExecution/requestApproval", "params": self._params(
            command="pwd", cwd=str(self.root), reason="作業場所の確認", startedAtMs=1,
            availableDecisions=[{"type": "acceptForSession"}, "accept", "decline", "cancel"],
        )})
        self.assertEqual(self.job.status, "waiting_approval")
        self.assertEqual(self.job.pending_details["decisions"], ["accept", "decline", "cancel"])

    def test_real_command_actions_allow_only_matching_safe_read_or_listing(self) -> None:
        """0.144.3 annotates safe wrapper commands with read/list actions."""
        skill = (SCRIPTS.parent / "SKILL.md").resolve()
        cases = [
            (
                f"/bin/zsh -c 'cat {skill}'",
                [{"type": "read", "command": f"cat {skill}", "name": "SKILL.md", "path": str(skill)}],
            ),
            (
                "/bin/sh -c 'rg --files .study/smoke'",
                [{"type": "listFiles", "command": "rg --files .study/smoke", "path": "smoke"}],
            ),
        ]
        for number, (command, actions) in enumerate(cases):
            self.manager._on_request({"id": f"real-action-{number}", "method": "item/commandExecution/requestApproval", "params": self._params(
                command=command, cwd=str(self.root), reason="内容の確認", startedAtMs=1,
                commandActions=actions, availableDecisions=["accept", "decline", "cancel"],
            )})
            self.assertEqual(self.job.status, "waiting_approval", command)
            self.manager.respond("job", {"decision": "decline"})

        for number, actions in enumerate([
            [{"type": "write", "command": "cat lesson.md", "path": str(self.root / "lesson.md")}],
            [{"type": "read", "command": "cat another.md", "name": "another.md", "path": str(self.root / "lesson.md")}],
            [{"type": "read", "command": "cat /tmp/outside.md", "name": "outside.md", "path": "/tmp/outside.md"}],
        ]):
            self.manager._on_request({"id": f"unsafe-action-{number}", "method": "item/commandExecution/requestApproval", "params": self._params(
                command="cat lesson.md", cwd=str(self.root), reason="内容の確認", startedAtMs=1,
                commandActions=actions, availableDecisions=["accept", "decline", "cancel"],
            )})
            self.assertEqual(self.capture.replies[-1], (f"unsafe-action-{number}", {"decision": "decline"}))
            self.assertEqual(self.job.status, "running")

    def test_shell_grammar_and_indirect_execution_cannot_bypass_command_proof(self) -> None:
        """Only a simple argv command may reach the browser approval card."""
        bypasses = [
            "touch ..{,}/escaped.md",
            "touch $'../escaped.md'",
            "cat <(python -c 'print(1)')",
            "find . -exec python -c 'print(1)' {} +",
            "eval 'python -c \"print(1)\"'",
        ]
        for request_id, command in enumerate(bypasses):
            self.manager._on_request({"id": f"bypass-{request_id}", "method": "item/commandExecution/requestApproval", "params": self._params(
                command=command, cwd=str(self.root), reason="実行", startedAtMs=1,
                availableDecisions=["accept", "decline", "cancel"],
            )})
            self.assertEqual(self.capture.replies[-1], (f"bypass-{request_id}", {"decision": "decline"}), command)
            self.assertEqual(self.job.status, "running", command)

        self.manager._on_request({"id": "simple-pwd", "method": "item/commandExecution/requestApproval", "params": self._params(
            command="pwd", cwd=str(self.root), reason="作業場所の確認", startedAtMs=1,
            availableDecisions=["accept", "decline", "cancel"],
        )})
        self.assertEqual(self.job.status, "waiting_approval")

    def test_inline_code_and_direct_interpreters_are_auto_denied(self) -> None:
        """A browser approval must never authorize code supplied on the command line."""
        inline_commands = [
            "sh -c 'printf inline'",
            "bash -c 'touch ../escaped.md'",
            "command bash -c 'touch ../escaped.md'",
            "command -- bash -c 'touch ../escaped.md'",
            "command -p bash -c 'touch ../escaped.md'",
            "env -- command -- bash -c 'touch ../escaped.md'",
            'bash -c "printf inline"',
            "zsh -c 'printf inline'",
            "fish -c 'printf inline'",
            "dash -c 'printf inline'",
            "python -c '__import__(\"pathlib\").Path(\"../escaped.md\").write_text(\"x\")'",
            'python3 -c "print(1)"',
            "env STUDY_LOOP_MODE=test python3 -c 'print(1)'",
            "exec python -c 'print(1)'",
            "env -S python -c 'print(1)'",
            "nice python -c 'print(1)'",
            "time python -c 'print(1)'",
            "noglob python -c 'print(1)'",
            "node -e 'console.log(1)'",
            "node --eval 'console.log(1)'",
            "ruby -e 'puts 1'",
            "ruby --eval 'puts 1'",
            "perl -e 'print 1'",
            "perl -E 'say 1'",
            "php -r 'echo 1'",
            "php --run 'echo 1'",
        ]
        for request_id, command in enumerate(inline_commands):
            self.manager._on_request({"id": f"inline-{request_id}", "method": "item/commandExecution/requestApproval", "params": self._params(
                command=command, cwd=str(self.root), reason="実行", startedAtMs=1,
                availableDecisions=["accept", "decline", "cancel"],
            )})
            self.assertEqual(self.capture.replies[-1], (f"inline-{request_id}", {"decision": "decline"}), command)
            self.assertEqual(self.job.status, "running", command)

        self.manager._on_request({"id": "inline-action", "method": "item/commandExecution/requestApproval", "params": self._params(
            command="touch lesson.md", cwd=str(self.root), reason="実行", startedAtMs=1,
            commandActions=[{"type": "unknown", "command": "python -c '__import__(\"pathlib\").Path(\"../escaped.md\").write_text(\"x\")'"}],
            availableDecisions=["accept", "decline", "cancel"],
        )})
        self.assertEqual(self.capture.replies[-1], ("inline-action", {"decision": "decline"}))
        self.assertEqual(self.job.status, "running")

        for request_id, command in enumerate([
            "python -m unittest",
            "python3 -m pip --version",
            "python3 lesson.py",
            "node lesson.js",
            "ruby lesson.rb",
            "perl lesson.pl",
            "php lesson.php",
            "bash lesson.sh",
        ]):
            self.manager._on_request({"id": f"direct-{request_id}", "method": "item/commandExecution/requestApproval", "params": self._params(
                command=command, cwd=str(self.root), reason="実行", startedAtMs=1,
                availableDecisions=["accept", "decline", "cancel"],
            )})
            self.assertEqual(self.capture.replies[-1], (f"direct-{request_id}", {"decision": "decline"}), command)
            self.assertEqual(self.job.status, "running", command)

    def test_known_system_shell_wrapper_allows_a_single_safe_local_command(self) -> None:
        """Only non-login system wrappers may enclose one proven local command."""
        self.manager._on_request({"id": "shell-pwd", "method": "item/commandExecution/requestApproval", "params": self._params(
            command="/bin/zsh -c pwd", cwd=str(self.root), reason="作業場所の確認", startedAtMs=1,
            availableDecisions=["accept", "decline", "cancel"],
        )})

        self.assertEqual(self.job.status, "waiting_approval")
        self.assertEqual(self.job.pending_details["command"], "/bin/zsh -c pwd")
        self.assertEqual(self.capture.replies, [])

        self.manager.respond("job", {"decision": "decline"})
        for request_id, command in enumerate([
            "/bin/zsh -lc pwd",
            "/bin/zsh -lc 'touch ../escaped.md'",
            "/bin/zsh -lc 'echo $HOME'",
            "/bin/zsh -lc 'pwd | cat'",
            "/bin/zsh -lc 'pwd > output.txt'",
            "/bin/zsh -lc \"python -c 'print(1)'\"",
            "/bin/zsh -lc '=(python -c print(1))'",
        ]):
            self.manager._on_request({"id": f"unsafe-shell-{request_id}", "method": "item/commandExecution/requestApproval", "params": self._params(
                command=command, cwd=str(self.root), reason="実行", startedAtMs=1,
                availableDecisions=["accept", "decline", "cancel"],
            )})
            self.assertEqual(self.capture.replies[-1], (f"unsafe-shell-{request_id}", {"decision": "decline"}), command)
            self.assertEqual(self.job.status, "running", command)

    def test_codex_apply_patch_launcher_is_the_only_write_command_approval(self) -> None:
        """Only Codex's fixed launcher may bridge to the separate file card."""
        launcher = self.root / "codex-arg0safe" / "apply_patch"
        launcher.parent.mkdir()
        launcher.write_text("#!/bin/sh\n", encoding="utf-8")
        launcher.chmod(0o755)
        self.manager._apply_patch_launcher = launcher

        safe = "/bin/zsh -c apply_patch"
        self.manager._on_request({"id": "apply-safe", "method": "item/commandExecution/requestApproval", "params": self._params(
            command=safe, cwd=str(self.root), reason="更新", startedAtMs=1,
            commandActions=[{"type": "unknown", "command": "apply_patch"}],
            availableDecisions=["accept", "decline", "cancel"],
        )})
        self.assertEqual(self.job.status, "waiting_approval")
        self.assertEqual(self.job.pending_details["command"], safe)
        self.manager.respond("job", {"decision": "decline"})

        rejected = [
            ("apply_patch", [{"type": "unknown", "command": "apply_patch"}]),
            ("/bin/sh -c apply_patch", [{"type": "unknown", "command": "apply_patch"}]),
            ("/bin/zsh -c 'apply_patch --unsafe'", [{"type": "unknown", "command": "apply_patch --unsafe"}]),
            ("/bin/zsh -c apply_patch", [{"type": "unknown", "command": "apply_patch", "path": "lesson.md"}]),
            ("/bin/zsh -c apply_patch", [{"type": "write", "command": "apply_patch", "path": "lesson.md"}]),
        ]
        for number, (command, actions) in enumerate(rejected):
            self.manager._on_request({"id": f"apply-rejected-{number}", "method": "item/commandExecution/requestApproval", "params": self._params(
                command=command, cwd=str(self.root), reason="更新", startedAtMs=1,
                commandActions=actions, availableDecisions=["accept", "decline", "cancel"],
            )})
            self.assertEqual(self.capture.replies[-1], (f"apply-rejected-{number}", {"decision": "decline"}), command)
            self.assertEqual(self.job.status, "running", command)

    def test_real_apply_patch_wrapper_accepts_only_active_topic_markdown(self) -> None:
        """The 0.144.3 zsh wrapper carries a literal, scoped patch argument."""
        launcher = self.root / "codex-arg0safe" / "apply_patch"
        launcher.parent.mkdir()
        launcher.write_text("#!/bin/sh\n", encoding="utf-8")
        launcher.chmod(0o755)
        self.manager._apply_patch_launcher = launcher
        lesson = self.root / ".study" / "python" / "lessons" / "01.md"
        lesson.parent.mkdir(parents=True)
        lesson.write_text("# Lesson\n", encoding="utf-8")
        patch = """*** Begin Patch
*** Update File: .study/python/lessons/01.md
@@
-# Lesson
+# Lesson: 採点済み
*** Add File: .study/python/lessons/02.md
+# 次の Lesson
*** End Patch"""
        command = f"/bin/zsh -c {shlex.quote(f'apply_patch {shlex.quote(patch)}')}"
        action = {"type": "unknown", "command": f"apply_patch {shlex.quote(patch)}"}
        self.manager._on_request({"id": "real-apply-patch", "method": "item/commandExecution/requestApproval", "params": self._params(
            command=command, cwd=str(self.root), reason="Markdown を更新", startedAtMs=1,
            commandActions=[action], availableDecisions=["accept", "decline", "cancel"],
        )})
        self.assertEqual(self.job.status, "waiting_approval")
        self.assertEqual(self.job.pending_details["command"], command)
        self.manager.respond("job", {"decision": "decline"})

        outside_patch = patch.replace(".study/python/lessons/02.md", ".study/other/lessons/02.md")
        escaped_patch = patch.replace(".study/python/lessons/02.md", ".study/python/lessons/../escape.md")
        outside = self.root.parent / "patch-outside.md"
        outside.write_text("outside", encoding="utf-8")
        (self.root / ".study" / "python" / "linked").symlink_to(outside.parent, target_is_directory=True)
        symlink_patch = patch.replace(".study/python/lessons/02.md", ".study/python/linked/patch-outside.md")
        missing_update_patch = patch.replace(".study/python/lessons/01.md", ".study/python/lessons/missing.md")
        non_markdown_patch = patch.replace(".study/python/lessons/02.md", ".study/python/lessons/02.txt")
        delete_patch = """*** Begin Patch
*** Delete File: .study/python/lessons/01.md
*** End Patch"""
        malformed_patch = "Update File: .study/python/lessons/01.md"
        rejected: list[tuple[str, list[dict[str, str]]]] = []
        for candidate in [
            outside_patch, escaped_patch, symlink_patch, missing_update_patch,
            non_markdown_patch, delete_patch, malformed_patch, patch + ("x" * 70_000),
        ]:
            inner = f"apply_patch {shlex.quote(candidate)}"
            rejected.append((f"/bin/zsh -c {shlex.quote(inner)}", [{"type": "unknown", "command": inner}]))
        rejected.extend([
            (f"/bin/zsh -c {shlex.quote('apply_patch $(pwd)')}", [{"type": "unknown", "command": "apply_patch $(pwd)"}]),
            (command + " ignored", [action]),
            (command, [{"type": "unknown", "command": "apply_patch"}]),
        ])
        for number, (unsafe_command, unsafe_actions) in enumerate(rejected):
            self.manager._on_request({"id": f"real-apply-patch-rejected-{number}", "method": "item/commandExecution/requestApproval", "params": self._params(
                command=unsafe_command, cwd=str(self.root), reason="更新", startedAtMs=1,
                commandActions=unsafe_actions, availableDecisions=["accept", "decline", "cancel"],
            )})
            self.assertEqual(self.capture.replies[-1], (f"real-apply-patch-rejected-{number}", {"decision": "decline"}), unsafe_command)
            self.assertEqual(self.job.status, "running", unsafe_command)

    def test_apply_patch_flow_writes_only_after_file_change_acceptance(self) -> None:
        """The launcher approval never substitutes for a project-local file approval."""
        root_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(root_tmp.cleanup)
        project = Path(root_tmp.name)
        client = _ApplyPatchFlowClient()
        manager = JobManager(project_root=project, client_factory=lambda: client)
        self.addCleanup(manager.close)
        launcher = project / "trusted" / "apply_patch"
        launcher.parent.mkdir()
        launcher.write_text("#!/bin/sh\n", encoding="utf-8")
        launcher.chmod(0o755)
        manager._apply_patch_launcher = launcher
        client.apply_patch_launcher = launcher
        target = project / ".study" / "python" / "diagnostic" / "01.md"
        job = manager.create_job("session_start", "python", {"topic": "Python"})
        deadline = time.monotonic() + 1
        while manager.get_job(job.id).status != "waiting_approval" and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(manager.get_job(job.id).pending_request_id, "apply-launcher")
        self.assertFalse(target.exists())

        manager.respond(job.id, {"decision": "accept"})
        self.assertEqual(manager.get_job(job.id).pending_request_id, "file-change")
        self.assertFalse(target.exists())

        manager.respond(job.id, {"decision": "accept"})
        while manager.get_job(job.id).status not in {"completed", "failed"} and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(manager.get_job(job.id).status, "completed")
        self.assertTrue(target.is_file())

    def test_path_hijacks_and_untrusted_absolute_executables_are_rejected(self) -> None:
        """Approval follows the frozen executable map, never the caller's PATH."""
        original = self.manager._approved_executables["cat"]
        fake = self.root / "cat"
        fake.write_text("not executable", encoding="utf-8")
        fake.chmod(0o755)
        for command in ["./cat lesson.md", f"{fake} lesson.md", "/tmp/cat lesson.md"]:
            self.manager._on_request({"id": command, "method": "item/commandExecution/requestApproval", "params": self._params(
                command=command, cwd=str(self.root), reason="内容の確認", startedAtMs=1,
                availableDecisions=["accept", "decline", "cancel"],
            )})
            self.assertEqual(self.capture.replies[-1], (command, {"decision": "decline"}))
        old_path = os.environ.get("PATH")
        os.environ["PATH"] = str(self.root) + os.pathsep + (old_path or "")
        self.addCleanup(lambda: os.environ.__setitem__("PATH", old_path) if old_path is not None else os.environ.pop("PATH", None))
        self.manager._on_request({"id": "bare-cat-after-path-hijack", "method": "item/commandExecution/requestApproval", "params": self._params(
            command="cat lesson.md", cwd=str(self.root), reason="内容の確認", startedAtMs=1,
            availableDecisions=["accept", "decline", "cancel"],
        )})
        self.assertEqual(self.job.status, "waiting_approval")
        self.assertTrue(original.is_absolute())

    def test_session_end_requires_substantive_summary_text(self) -> None:
        """Structural Markdown alone must not count as a completed-session recap."""
        prefix = "# Study Loop: Python\n\n**Ended**: 2026-07-19\n\n## Summary\n\n"
        self.assertFalse(server._valid_session_end(prefix + "---\n"))
        self.assertFalse(server._valid_session_end(prefix + "- \n- \n"))
        self.assertTrue(server._valid_session_end(prefix + "次回は辞書内包表記を復習する。\n"))

    def test_unknown_or_mismatched_server_requests_cannot_control_the_active_job(self) -> None:
        self.manager._on_request({"id": "late", "method": "item/tool/requestUserInput", "params": self._params(threadId="other", questions=[])})
        self.assertEqual(self.capture.replies, [])

        self.manager._on_request({"id": "unknown", "method": "item/unknown/request", "params": self._params()})
        self.assertEqual(self.capture.errors[-1][0], "unknown")
        self.assertEqual(self.capture.errors[-1][1], -32601)
        self.assertEqual(self.job.status, "running")
        self.assertFalse(self.job.done.is_set())
        self.manager._on_notification({"method": "turn/completed", "params": {
            "threadId": "thread-1", "turn": {"id": "turn-1", "status": "failed"},
        }})
        self.assertEqual(self.job.status, "failed")

    def test_mcp_or_collaboration_item_started_fails_and_interrupts_the_turn(self) -> None:
        """A disabled integration is still a hard stop if the server emits it."""
        for item_type, item in [
            ("mcpToolCall", {"id": "mcp-1", "type": "mcpToolCall", "server": "unexpected", "tool": "read", "arguments": {}, "status": "inProgress"}),
            ("collabAgentToolCall", {"id": "agent-1", "type": "collabAgentToolCall", "tool": "spawnAgent", "senderThreadId": "thread-1", "receiverThreadIds": [], "agentsStates": {}, "status": "inProgress"}),
        ]:
            notification = {"method": "item/started", "params": {
                "threadId": "thread-1", "turnId": "turn-1", "startedAtMs": 1, "item": item,
            }}
            validate_jsonrpc_fixture([], {}, [notification])
            self.job.status = "running"
            self.job.done.clear()
            self.job.failure_pending = False
            self.manager._on_notification(notification)
            self.assertEqual(self.job.status, "running", item_type)
            self.assertFalse(self.job.done.is_set(), item_type)
            self.assertIn("許可されていない", self.job.error or "", item_type)
            self.assertEqual(self.capture.interrupts[-1], ("thread-1", "turn-1"), item_type)
            self.manager._on_notification({"method": "turn/completed", "params": {
                "threadId": "thread-1", "turn": {"id": "turn-1", "status": "interrupted"},
            }})
            self.assertEqual(self.job.status, "failed", item_type)
            self.assertTrue(self.job.done.is_set(), item_type)

    def test_turn_completion_requires_the_matching_completed_turn_and_never_emits_agent_delta(self) -> None:
        before = len(self.job.events)
        self.manager._on_notification({"method": "item/agentMessage/delta", "params": self._params(delta='{"status":"completed","summary":"ok","resultPath":null,"nextAction":"done"}')})
        self.assertEqual(len(self.job.events), before)
        self.manager._on_notification({"method": "turn/completed", "params": {
            "threadId": "thread-1", "turn": {"id": "turn-1", "status": "cancelled"},
        }})
        self.assertEqual(self.job.status, "failed")

        self.job.status = "running"
        self.job.done.clear()
        self.manager._on_notification({"method": "turn/completed", "params": {
            "threadId": "thread-1", "turn": {"id": "turn-1"},
        }})
        self.assertEqual(self.job.status, "failed")

    def test_completed_agent_message_is_authoritative_over_streamed_deltas(self) -> None:
        """Codex 0.144.3 may send both a streamed delta and the final item."""
        streamed = '{"status":"completed","summary":"streamed","resultPath":null,"nextAction":"done"}'
        final = '{"status":"completed","summary":"final","resultPath":null,"nextAction":"done"}'
        self.manager._on_notification({"method": "item/agentMessage/delta", "params": self._params(delta=streamed)})
        self.manager._on_notification({"method": "item/completed", "params": {
            **self._params(), "completedAtMs": 1,
            "item": {"id": "item-1", "type": "agentMessage", "phase": None, "text": final},
        }})
        self.manager._on_notification({"method": "turn/completed", "params": {
            "threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed"},
        }})

        self.assertEqual(self.job.status, "completed")
        self.assertEqual(self.job.result, {"status": "completed", "summary": "final", "resultPath": None, "nextAction": "done"})
        self.assertEqual(self.job.agent_text, streamed)

    def test_completed_agent_message_skips_commentary_and_other_item_types(self) -> None:
        delta = '{"status":"completed","summary":"delta","resultPath":null,"nextAction":"done"}'
        self.manager._on_notification({"method": "item/agentMessage/delta", "params": self._params(delta=delta)})
        for item in [
            {"id": "commentary", "type": "agentMessage", "phase": "commentary", "text": "not a result"},
            {"id": "tool", "type": "commandExecution", "status": "completed", "command": "pwd"},
        ]:
            self.manager._on_notification({"method": "item/completed", "params": {
                **self._params(), "completedAtMs": 1, "item": item,
            }})
        self.manager._on_notification({"method": "turn/completed", "params": {
            "threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed"},
        }})

        self.assertEqual(self.job.status, "completed")
        self.assertEqual(self.job.result, {"status": "completed", "summary": "delta", "resultPath": None, "nextAction": "done"})

    def test_completed_agent_message_with_mismatched_ids_cannot_replace_a_valid_delta(self) -> None:
        delta = '{"status":"completed","summary":"delta","resultPath":null,"nextAction":"done"}'
        self.manager._on_notification({"method": "item/agentMessage/delta", "params": self._params(delta=delta)})
        self.manager._on_notification({"method": "item/completed", "params": {
            "threadId": "other-thread", "turnId": "turn-1", "completedAtMs": 1,
            "item": {"id": "item-1", "type": "agentMessage", "phase": None, "text": "not json"},
        }})
        self.manager._on_notification({"method": "turn/completed", "params": {
            "threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed"},
        }})

        self.assertEqual(self.job.status, "completed")
        self.assertEqual(self.job.result, {"status": "completed", "summary": "delta", "resultPath": None, "nextAction": "done"})

    def test_phase_null_non_json_completed_message_keeps_its_valid_delta(self) -> None:
        delta = '{"status":"completed","summary":"delta","resultPath":null,"nextAction":"done"}'
        self.manager._on_notification({"method": "item/agentMessage/delta", "params": self._params(delta=delta)})
        self.manager._on_notification({"method": "item/completed", "params": {
            **self._params(), "completedAtMs": 1,
            "item": {"id": "item-1", "type": "agentMessage", "phase": None, "text": "not json"},
        }})
        self.manager._on_notification({"method": "turn/completed", "params": {
            "threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed"},
        }})

        self.assertEqual(self.job.status, "completed")
        self.assertEqual(self.job.result, {"status": "completed", "summary": "delta", "resultPath": None, "nextAction": "done"})

    def test_turn_completed_items_supply_a_valid_final_message_when_item_notification_is_missing(self) -> None:
        final = '{"status":"completed","summary":"turn item","resultPath":null,"nextAction":"done"}'
        self.manager._on_notification({"method": "turn/completed", "params": {
            "threadId": "thread-1", "turn": {
                "id": "turn-1", "status": "completed", "items": [
                    {"id": "item-1", "type": "agentMessage", "phase": None, "text": final},
                ],
            },
        }})

        self.assertEqual(self.job.status, "completed")
        self.assertEqual(self.job.result, {"status": "completed", "summary": "turn item", "resultPath": None, "nextAction": "done"})

    def test_completed_item_uses_only_deltas_from_its_own_item_id(self) -> None:
        first = '{"status":"completed","summary":"first","resultPath":null,"nextAction":"done"}'
        second = '{"status":"completed","summary":"second","resultPath":null,"nextAction":"done"}'
        self.manager._on_notification({"method": "item/agentMessage/delta", "params": self._params(itemId="first", delta=first)})
        self.manager._on_notification({"method": "item/agentMessage/delta", "params": self._params(itemId="second", delta=second)})
        self.manager._on_notification({"method": "item/completed", "params": {
            **self._params(), "completedAtMs": 1,
            "item": {"id": "first", "type": "agentMessage", "phase": "final_answer", "text": "not json"},
        }})
        self.manager._on_notification({"method": "turn/completed", "params": {
            "threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed"},
        }})

        self.assertEqual(self.job.status, "completed")
        self.assertEqual(self.job.result, {"status": "completed", "summary": "first", "resultPath": None, "nextAction": "done"})

    def test_late_notifications_after_completion_are_ignored(self) -> None:
        first = '{"status":"completed","summary":"first","resultPath":null,"nextAction":"done"}'
        second = '{"status":"completed","summary":"second","resultPath":null,"nextAction":"done"}'
        self.manager._on_notification({"method": "item/agentMessage/delta", "params": self._params(delta=first)})
        self.manager._on_notification({"method": "turn/completed", "params": {
            "threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed"},
        }})
        event_count = len(self.job.events)
        self.manager._on_notification({"method": "item/completed", "params": {
            **self._params(), "completedAtMs": 2,
            "item": {"id": "item-1", "type": "agentMessage", "phase": "final_answer", "text": second},
        }})
        self.manager._on_notification({"method": "turn/completed", "params": {
            "threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed"},
        }})

        self.assertEqual(self.job.status, "completed")
        self.assertEqual(self.job.result, {"status": "completed", "summary": "first", "resultPath": None, "nextAction": "done"})
        self.assertEqual(len(self.job.events), event_count)


class LockLifetimeTests(unittest.TestCase):
    def test_cancel_between_turn_id_assignment_and_post_start_handling_sends_one_interrupt(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        client = _ControlledStartClient()
        manager = JobManager(project_root=Path(tmp.name), client_factory=lambda: client)
        self.addCleanup(manager.close)
        job = manager.create_job("session_start", "python", {"topic": "Python"})
        self.assertTrue(client.start_entered.wait(0.2))
        original_setattr = Job.__setattr__
        cancelled = False

        def set_turn_and_cancel(instance, name, value):
            nonlocal cancelled
            original_setattr(instance, name, value)
            if instance is job and name == "turn_id" and value == "terminal-less-turn" and not cancelled:
                cancelled = True
                manager.cancel(job.id)

        with mock.patch.object(Job, "__setattr__", set_turn_and_cancel):
            client.allow_return.set()
            deadline = time.monotonic() + 0.5
            while len(client.interrupts) < 2 and time.monotonic() < deadline:
                time.sleep(0.005)

        self.assertEqual(client.interrupts, [("terminal-less-thread", "terminal-less-turn")])

    def test_cancel_requested_during_start_turn_sends_one_interrupt_after_ids_are_attached(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        client = _CancelDuringStartClient()
        manager = JobManager(project_root=Path(tmp.name), client_factory=lambda: client)
        self.addCleanup(manager.close)
        job = manager.create_job("session_start", "python", {"topic": "Python"})
        self.assertTrue(client.start_entered.wait(0.2))
        client.cancel_callback = lambda: manager.cancel(job.id)
        client.allow_return.set()
        deadline = time.monotonic() + 0.5
        while len(client.interrupts) < 1 and time.monotonic() < deadline:
            time.sleep(0.005)
        manager.cancel(job.id)
        time.sleep(0.02)

        self.assertEqual(client.interrupts, [("terminal-less-thread", "terminal-less-turn")])

    def test_failed_stop_retries_until_late_process_exit_is_confirmed(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        client = _LateExitClient()
        released = threading.Event()

        @contextmanager
        def topic_lock(_topic: str):
            try:
                yield
            finally:
                released.set()

        manager = JobManager(
            project_root=Path(tmp.name), client_factory=lambda: client, topic_lock=topic_lock,
            cancel_timeout_seconds=0.02,
        )
        self.addCleanup(manager.close)
        job = manager.create_job("session_start", "python", {"topic": "Python"})
        deadline = time.monotonic() + 1
        while manager.get_job(job.id).turn_id is None and time.monotonic() < deadline:
            time.sleep(0.01)
        manager._on_notification({"method": "item/started", "params": {
            "threadId": "terminal-less-thread", "turnId": "terminal-less-turn",
            "item": {"type": "mcpToolCall"},
        }})

        while manager.get_job(job.id).status != "failed" and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertGreaterEqual(client.termination_attempts, 2)
        self.assertEqual(manager.get_job(job.id).status, "failed")
        self.assertTrue(released.wait(0.2))

    def test_forbidden_integration_waits_for_terminal_turn_before_releasing_topic_lock(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        client = _TerminalLessClient()
        entered = threading.Event()
        released = threading.Event()

        @contextmanager
        def topic_lock(topic: str):
            self.assertEqual(topic, "python")
            entered.set()
            try:
                yield
            finally:
                released.set()

        manager = JobManager(project_root=Path(tmp.name), client_factory=lambda: client, topic_lock=topic_lock)
        self.addCleanup(manager.close)
        job = manager.create_job("session_start", "python", {"topic": "Python"})
        deadline = time.monotonic() + 1
        while manager.get_job(job.id).turn_id is None and time.monotonic() < deadline:
            time.sleep(0.01)

        manager._on_notification({"method": "item/started", "params": {
            "threadId": "terminal-less-thread", "turnId": "terminal-less-turn",
            "item": {"type": "mcpToolCall"},
        }})

        self.assertTrue(entered.is_set())
        self.assertEqual(manager.get_job(job.id).status, "running")
        self.assertFalse(manager.get_job(job.id).done.is_set())
        self.assertFalse(released.is_set())
        self.assertEqual(client.interrupts, [("terminal-less-thread", "terminal-less-turn")])
        with self.assertRaises(ValueError):
            manager.create_job("session_start", "python", {"topic": "Python"})

        manager._on_notification({"method": "turn/completed", "params": {
            "threadId": "terminal-less-thread",
            "turn": {"id": "terminal-less-turn", "status": "interrupted"},
        }})
        self.assertTrue(released.wait(0.2))
        self.assertEqual(manager.get_job(job.id).status, "failed")

    def test_unsupported_server_request_waits_for_terminal_turn_before_releasing_topic_lock(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        client = _TerminalLessClient()
        released = threading.Event()

        @contextmanager
        def topic_lock(_topic: str):
            try:
                yield
            finally:
                released.set()

        manager = JobManager(project_root=Path(tmp.name), client_factory=lambda: client, topic_lock=topic_lock)
        self.addCleanup(manager.close)
        job = manager.create_job("session_start", "python", {"topic": "Python"})
        deadline = time.monotonic() + 1
        while manager.get_job(job.id).turn_id is None and time.monotonic() < deadline:
            time.sleep(0.01)

        manager._on_request({"id": "unsupported", "method": "future/request", "params": {
            "threadId": "terminal-less-thread", "turnId": "terminal-less-turn",
        }})

        self.assertEqual(manager.get_job(job.id).status, "running")
        self.assertFalse(manager.get_job(job.id).done.is_set())
        self.assertFalse(released.is_set())
        self.assertEqual(client.errors[-1][0], "unsupported")
        self.assertEqual(client.interrupts, [("terminal-less-thread", "terminal-less-turn")])
        with self.assertRaises(ValueError):
            manager.create_job("session_start", "python", {"topic": "Python"})

        manager._on_notification({"method": "turn/completed", "params": {
            "threadId": "terminal-less-thread",
            "turn": {"id": "terminal-less-turn", "status": "failed"},
        }})
        self.assertTrue(released.wait(0.2))
        self.assertEqual(manager.get_job(job.id).status, "failed")

    def test_transport_failure_while_waiting_clears_pending_browser_request(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        client = _BlockingClient()
        manager = JobManager(project_root=Path(tmp.name), client_factory=lambda: client)
        self.addCleanup(manager.close)
        job = manager.create_job("session_start", "python", {"topic": "Python"})
        deadline = time.monotonic() + 1
        while manager.get_job(job.id).status != "waiting_input" and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertEqual(manager.get_job(job.id).status, "waiting_input")
        client.crashed = True
        while manager.get_job(job.id).status != "failed" and time.monotonic() < deadline:
            time.sleep(0.01)

        failed = manager.get_job(job.id)
        self.assertEqual(failed.status, "failed")
        self.assertIsNone(failed.pending_request_id)
        self.assertIsNone(failed.pending_kind)
        self.assertIsNone(failed.pending_details)

    def test_cancel_timeout_terminates_the_process_before_releasing_the_topic_lock(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        first = _TerminalLessClient()
        second = _CompletingClient()
        clients = iter([first, second])
        entered: list[tuple[str, bool]] = []

        @contextmanager
        def topic_lock(topic: str):
            entered.append((topic, first.terminated.is_set()))
            yield

        manager = JobManager(
            project_root=Path(tmp.name), client_factory=lambda: next(clients), topic_lock=topic_lock,
            cancel_timeout_seconds=0.02,
        )
        self.addCleanup(manager.close)
        first_job = manager.create_job("session_start", "python", {"topic": "Python"})
        deadline = time.monotonic() + 1
        while manager.get_job(first_job.id).turn_id is None and time.monotonic() < deadline:
            time.sleep(0.005)
        manager.cancel(first_job.id)
        while manager.get_job(first_job.id).status != "cancelled" and time.monotonic() < deadline:
            time.sleep(0.005)
        second_job = manager.create_job("session_start", "python", {"topic": "Python"})
        while manager.get_job(second_job.id).status not in {"completed", "failed"} and time.monotonic() < deadline:
            time.sleep(0.005)

        self.assertTrue(first.terminated.is_set())
        self.assertEqual(manager.get_job(first_job.id).status, "cancelled")
        self.assertEqual(entered, [("python", False), ("python", True)])

    def test_topic_lock_covers_waiting_for_a_browser_answer_until_turn_completion(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        entered = threading.Event()
        released = threading.Event()
        client = _BlockingClient()

        @contextmanager
        def topic_lock(topic: str):
            self.assertEqual(topic, "python")
            entered.set()
            try:
                yield
            finally:
                released.set()

        manager = JobManager(project_root=Path(tmp.name), client_factory=lambda: client, topic_lock=topic_lock)
        self.addCleanup(manager.close)
        job = manager.create_job("session_start", "python", {"topic": "Python"})
        deadline = time.monotonic() + 1
        while manager.get_job(job.id).status != "waiting_input" and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertTrue(entered.is_set())
        self.assertFalse(released.is_set())
        manager.respond(job.id, {"answers": {"q": ["はい"]}})
        while manager.get_job(job.id).status != "completed" and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(released.wait(0.2))

    def test_request_arriving_before_turn_start_returns_is_replayed_after_id_correlation(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        client = _ImmediateRequestClient()
        manager = JobManager(project_root=Path(tmp.name), client_factory=lambda: client)
        self.addCleanup(manager.close)
        job = manager.create_job("session_start", "python", {"topic": "Python"})
        deadline = time.monotonic() + 1
        while manager.get_job(job.id).status != "waiting_input" and time.monotonic() < deadline:
            time.sleep(0.01)

        waiting = manager.get_job(job.id)
        self.assertEqual(waiting.status, "waiting_input")
        self.assertEqual(waiting.pending_request_id, "immediate")
        manager.respond(job.id, {"answers": {"q": ["はい"]}})
        deadline = time.monotonic() + 1
        while manager.get_job(job.id).status != "completed" and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(manager.get_job(job.id).status, "completed")

    def test_cancel_holds_the_topic_lock_until_a_matching_terminal_turn_event(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        entered = threading.Event()
        released = threading.Event()
        client = _BlockingClient()

        @contextmanager
        def topic_lock(topic: str):
            entered.set()
            try:
                yield
            finally:
                released.set()

        manager = JobManager(project_root=Path(tmp.name), client_factory=lambda: client, topic_lock=topic_lock)
        self.addCleanup(manager.close)
        job = manager.create_job("session_start", "python", {"topic": "Python"})
        deadline = time.monotonic() + 1
        while manager.get_job(job.id).status != "waiting_input" and time.monotonic() < deadline:
            time.sleep(0.01)
        manager.cancel(job.id)

        self.assertTrue(entered.is_set())
        self.assertEqual(manager.get_job(job.id).status, "running")
        self.assertEqual(manager.get_job(job.id).message, "停止中です。")
        self.assertFalse(released.is_set())
        manager._on_notification({"method": "turn/completed", "params": {
            "threadId": "thread", "turn": {"id": "turn", "status": "interrupted"},
        }})
        self.assertTrue(released.wait(0.2))
        self.assertEqual(manager.get_job(job.id).status, "cancelled")

    def test_confirmed_answer_revision_is_rechecked_inside_topic_lock_before_starting_turn(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        answer_file = root / ".study" / "python" / "lessons" / "01-code.md"
        answer_file.parent.mkdir(parents=True)
        answer_file.write_text("# Code\n\n## 回答欄\n\n元の答え\n", encoding="utf-8")
        revision = hashlib.sha256(answer_file.read_bytes()).hexdigest()
        client = _RevisionClient()

        @contextmanager
        def topic_lock(topic: str):
            answer_file.write_text("# Code\n\n## 回答欄\n\n編集後の答え\n", encoding="utf-8")
            yield

        manager = JobManager(project_root=root, client_factory=lambda: client, topic_lock=topic_lock)
        self.addCleanup(manager.close)
        job = manager.create_job("lesson_grade", "python", {
            "target": {"kind": "lessons", "name": "01-code.md"},
            "_confirmedAnswer": {"kind": "lessons", "name": "01-code.md", "revision": revision},
        })
        deadline = time.monotonic() + 1
        while manager.get_job(job.id).status not in {"completed", "failed"} and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertEqual(manager.get_job(job.id).status, "failed")
        self.assertEqual(client.start_calls, 0)


class WorkflowGuardTests(unittest.TestCase):
    def test_preflight_rechecks_session_start_and_existing_transition_after_queueing_inside_topic_lock(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        project = Path(tmp.name)
        root = project / ".study"
        root.mkdir()
        previous = {key: server.app.config.get(key) for key in ("ROOT", "PROJECT_ROOT")}
        self.addCleanup(lambda: server.app.config.update(previous))
        server.app.config.update(ROOT=root, PROJECT_ROOT=project)
        clients = [_NoStartClient(), _NoStartClient()]

        def wait_failed(manager: JobManager, job_id: str) -> None:
            deadline = time.monotonic() + 1
            while manager.get_job(job_id).status not in {"failed", "completed"} and time.monotonic() < deadline:
                time.sleep(0.005)
            self.assertEqual(manager.get_job(job_id).status, "failed")

        @contextmanager
        def session_start_lock(topic: str):
            (root / topic).mkdir()
            yield

        manager = JobManager(
            project_root=project, client_factory=lambda: clients[0], topic_lock=session_start_lock,
            preflight=server._preflight_workflow,
        )
        self.addCleanup(manager.close)
        started = manager.create_job("session_start", "python", {"topic": "Python"})
        wait_failed(manager, started.id)
        self.assertEqual(clients[0].start_calls, 0)

        topic = root / "existing"
        diagnostic = topic / "diagnostic"
        diagnostic.mkdir(parents=True)
        (topic / "README.md").write_text("# Study Loop: Existing\n", encoding="utf-8")
        for number in range(1, 5):
            (diagnostic / f"{number:02d}.md").write_text(f"# {number}\n\n## 採点\n\n**Score**: 8\n", encoding="utf-8")
        (diagnostic / "summary.md").write_text("# Summary\n", encoding="utf-8")

        @contextmanager
        def existing_lock(topic_name: str):
            (root / topic_name / "diagnostic" / "summary.md").unlink()
            yield

        existing_manager = JobManager(
            project_root=project, client_factory=lambda: clients[1], topic_lock=existing_lock,
            preflight=server._preflight_workflow,
        )
        self.addCleanup(existing_manager.close)
        accepted = existing_manager.create_job("diagnostic_accept", "existing", {})
        wait_failed(existing_manager, accepted.id)
        self.assertEqual(clients[1].start_calls, 0)

    def test_postflight_rejects_completion_while_the_topic_lock_is_still_held(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        entered = threading.Event()
        released = threading.Event()
        observed: list[bool] = []
        client = _ResultClient()

        @contextmanager
        def topic_lock(topic: str):
            entered.set()
            try:
                yield
            finally:
                released.set()

        def reject_postflight(action: str, topic: str, payload: dict[str, object], result: dict[str, object], snapshot: object) -> None:
            observed.append(entered.is_set() and not released.is_set())
            raise ValueError("missing Markdown postcondition")

        manager = JobManager(
            project_root=Path(tmp.name), client_factory=lambda: client, topic_lock=topic_lock,
            postflight=reject_postflight,
        )
        self.addCleanup(manager.close)
        job = manager.create_job("session_start", "python", {"topic": "Python"})
        deadline = time.monotonic() + 1
        while manager.get_job(job.id).status not in {"failed", "completed"} and time.monotonic() < deadline:
            time.sleep(0.005)

        self.assertEqual(manager.get_job(job.id).status, "failed")
        self.assertEqual(observed, [True])
        self.assertTrue(released.wait(0.2))


class WorkflowPostconditionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.root = self.project / ".study"
        self.root.mkdir()
        previous = {key: server.app.config.get(key) for key in ("ROOT", "PROJECT_ROOT")}
        self.addCleanup(lambda: server.app.config.update(previous))
        server.app.config.update(ROOT=self.root, PROJECT_ROOT=self.project)

    def _result(self, path: str | None, next_action: str) -> dict[str, object]:
        return {"status": "completed", "summary": "完了", "resultPath": path, "nextAction": next_action}

    def _card(self, path: Path, *, graded: bool) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        grading = "**Score**: 8" if graded else "_未採点_"
        path.write_text(f"# {path.stem}\n\n## 回答欄\n\n答え\n\n## 採点\n\n{grading}\n", encoding="utf-8")

    def _session(self, topic: str, *, ready: bool = False) -> Path:
        directory = self.root / topic
        directory.mkdir()
        (directory / "README.md").write_text(f"# Study Loop: {topic}\n", encoding="utf-8")
        (directory / "curriculum.md").write_text("# Curriculum\n", encoding="utf-8")
        if ready:
            (directory / "RESOURCES.md").write_text("# Resources\n", encoding="utf-8")
            for number in range(1, 5):
                self._card(directory / "diagnostic" / f"{number:02d}.md", graded=True)
            (directory / "diagnostic" / "summary.md").write_text("# Summary\n", encoding="utf-8")
        return directory

    def test_all_actions_require_real_markdown_postconditions_and_consistent_outcomes(self) -> None:
        # session_start creates a durable skeleton and an answerable diagnostic.
        start_snapshot = server._workflow_snapshot("start")
        start = self._session("start")
        self._card(start / "diagnostic" / "01.md", graded=False)
        server._validate_workflow_completion("session_start", "start", {}, self._result(".study/start/diagnostic/01.md", "answer"), start_snapshot)
        with self.assertRaises(ValueError):
            server._validate_workflow_completion("session_start", "start", {}, self._result(None, "done"), start_snapshot)

        # diagnostic_grade must grade its target and expose a real next question.
        diagnostic = self._session("diagnostic")
        self._card(diagnostic / "diagnostic" / "01.md", graded=False)
        diagnostic_snapshot = server._workflow_snapshot("diagnostic")
        self._card(diagnostic / "diagnostic" / "01.md", graded=True)
        self._card(diagnostic / "diagnostic" / "02.md", graded=False)
        server._validate_workflow_completion("diagnostic_grade", "diagnostic", {"target": {"kind": "diagnostic", "name": "01.md"}}, self._result(".study/diagnostic/diagnostic/02.md", "answer"), diagnostic_snapshot)
        with self.assertRaises(ValueError):
            server._validate_workflow_completion("diagnostic_grade", "diagnostic", {"target": {"kind": "diagnostic", "name": "01.md"}}, self._result(".study/diagnostic/diagnostic/01.md", "answer"), diagnostic_snapshot)

        final_diagnostic = self._session("final-diagnostic")
        for number in range(1, 5):
            self._card(final_diagnostic / "diagnostic" / f"{number:02d}.md", graded=number < 4)
        final_snapshot = server._workflow_snapshot("final-diagnostic")
        self._card(final_diagnostic / "diagnostic" / "04.md", graded=True)
        (final_diagnostic / "diagnostic" / "summary.md").write_text("# Summary\n", encoding="utf-8")
        server._validate_workflow_completion("diagnostic_grade", "final-diagnostic", {"target": {"kind": "diagnostic", "name": "04.md"}}, self._result(".study/final-diagnostic/diagnostic/summary.md", "review_curriculum"), final_snapshot)

        # diagnostic_accept creates the two curriculum assets.
        accepted = self._session("accepted", ready=True)
        accepted_snapshot = server._workflow_snapshot("accepted")
        with self.assertRaises(ValueError):
            server._validate_workflow_completion("diagnostic_accept", "accepted", {}, self._result(".study/accepted/curriculum.md", "review_curriculum"), accepted_snapshot)
        (accepted / "RESOURCES.md").write_text("# Resources\n\n選定済み\n", encoding="utf-8")
        server._validate_workflow_completion("diagnostic_accept", "accepted", {}, self._result(".study/accepted/curriculum.md", "review_curriculum"), accepted_snapshot)

        # curriculum_revise must have actually changed a durable curriculum asset.
        revised = self._session("revised", ready=True)
        revised_snapshot = server._workflow_snapshot("revised")
        (revised / "curriculum.md").write_text("# Curriculum\n\nUpdated\n", encoding="utf-8")
        server._validate_workflow_completion("curriculum_revise", "revised", {}, self._result(".study/revised/curriculum.md", "review_curriculum"), revised_snapshot)
        unchanged = self._session("unchanged", ready=True)
        with self.assertRaises(ValueError):
            server._validate_workflow_completion("curriculum_revise", "unchanged", {}, self._result(".study/unchanged/curriculum.md", "review_curriculum"), server._workflow_snapshot("unchanged"))

        # curriculum_accept, lesson_grade, and spaced_review must make a new answerable lesson where required.
        curriculum = self._session("curriculum", ready=True)
        curriculum_snapshot = server._workflow_snapshot("curriculum")
        self._card(curriculum / "lessons" / "01.md", graded=False)
        server._validate_workflow_completion("curriculum_accept", "curriculum", {}, self._result(".study/curriculum/lessons/01.md", "answer"), curriculum_snapshot)

        lesson = self._session("lesson", ready=True)
        self._card(lesson / "lessons" / "01.md", graded=False)
        lesson_snapshot = server._workflow_snapshot("lesson")
        self._card(lesson / "lessons" / "01.md", graded=True)
        self._card(lesson / "lessons" / "02.md", graded=False)
        server._validate_workflow_completion("lesson_grade", "lesson", {"target": {"kind": "lessons", "name": "01.md"}}, self._result(".study/lesson/lessons/02.md", "answer"), lesson_snapshot)

        retry = self._session("retry", ready=True)
        self._card(retry / "lessons" / "01.md", graded=True)
        retry_snapshot = server._workflow_snapshot("retry")
        self._card(retry / "lessons" / "retry-02.md", graded=False)
        server._validate_workflow_completion("lesson_grade", "retry", {"resolution": "retry"}, self._result(".study/retry/lessons/retry-02.md", "answer"), retry_snapshot)

        review = self._session("review", ready=True)
        self._card(review / "lessons" / "01.md", graded=True)
        review_snapshot = server._workflow_snapshot("review")
        self._card(review / "lessons" / "review-02.md", graded=False)
        server._validate_workflow_completion("spaced_review", "review", {}, self._result(".study/review/lessons/review-02.md", "answer"), review_snapshot)

        ended = self._session("ended", ready=True)
        end_snapshot = server._workflow_snapshot("ended")
        (ended / "README.md").write_text("# Study Loop: ended\n\n**Ended**: 2026-07-19\n\n## Summary\n\n完了\n", encoding="utf-8")
        server._validate_workflow_completion("session_end", "ended", {}, self._result(".study/ended/README.md", "done"), end_snapshot)
        with self.assertRaises(ValueError):
            server._validate_workflow_completion("session_end", "ended", {}, self._result(".study/ended/README.md", "done"), server._workflow_snapshot("ended"))
        with self.assertRaises(server.InvalidTransition):
            server._preflight_workflow("session_end", "ended", {})

    def test_lesson_grade_done_may_report_its_graded_lesson_only(self) -> None:
        lesson = self._session("lesson-done", ready=True)
        self._card(lesson / "lessons" / "01.md", graded=True)
        payload = {"target": {"kind": "lessons", "name": "01.md"}}
        snapshot = server._workflow_snapshot("lesson-done")

        server._validate_workflow_completion(
            "lesson_grade",
            "lesson-done",
            payload,
            self._result(".study/lesson-done/lessons/01.md", "done"),
            snapshot,
        )

        for result_path in (
            ".study/lesson-done/lessons/02.md",
            ".study/lesson-done/curriculum.md",
            "/tmp/outside.md",
        ):
            with self.assertRaises(ValueError):
                server._validate_workflow_completion(
                    "lesson_grade",
                    "lesson-done",
                    payload,
                    self._result(result_path, "done"),
                    snapshot,
                )

class ConfirmationAndRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / ".study"
        self.topic_dir = self.root / "python"
        (self.topic_dir / "diagnostic").mkdir(parents=True)
        (self.topic_dir / "README.md").write_text("# Study Loop: Python\n", encoding="utf-8")
        server.app.config.update(
            TESTING=True,
            ROOT=self.root,
            PROJECT_ROOT=self.root.parent,
            BACKEND="codex",
            JOB_MANAGER=_RouteManager(),
            CODEX_PATH="/usr/local/bin/codex",
            CONFIRMATIONS={},
        )
        self.client = server.app.test_client()
        with self.client.session_transaction() as session:
            session["csrf_token"] = "test-csrf"

    def _headers(self) -> dict[str, str]:
        return {"X-CSRF-Token": "test-csrf", "Origin": "http://localhost"}

    def _write_diagnostic(self, name: str, *, graded: bool = False) -> Path:
        path = self.topic_dir / "diagnostic" / name
        grading = "**Score**: 8" if graded else "_未採点_"
        path.write_text(f"# {name}\n\n## 回答欄\n\n答え\n\n---\n\n## 採点\n\n{grading}\n", encoding="utf-8")
        return path

    def test_confirmation_token_is_stale_after_edit_and_single_use_after_job_creation(self) -> None:
        target = self._write_diagnostic("01-basics.md")
        token = server._new_confirmation("python", "diagnostic", target.name, target, "答え", [], "")
        target.write_text(target.read_text(encoding="utf-8") + "更新", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "変更"):
            server._confirmation_record(token)

        target = self._write_diagnostic("01-basics.md")
        token = server._new_confirmation("python", "diagnostic", target.name, target, "答え", ["基本"], "補足")
        payload = {"action": "diagnostic_grade", "data": {"confirmationToken": token, "selfExplanation": "理由"}}
        first = self.client.post("/api/jobs", json=payload, headers=self._headers())
        replay = self.client.post("/api/jobs", json=payload, headers=self._headers())

        self.assertEqual(first.status_code, 202)
        self.assertEqual(replay.status_code, 400)
        call = server.app.config["JOB_MANAGER"].calls[0]
        self.assertEqual(call[1], "python")
        self.assertEqual(call[2]["target"], {"kind": "diagnostic", "name": "01-basics.md"})
        self.assertNotIn("confirmationToken", call[2])

    def test_completed_job_has_server_routed_next_url_and_diagnostic_gate(self) -> None:
        for number in range(1, 5):
            self._write_diagnostic(f"{number:02d}-check.md", graded=True)
        (self.topic_dir / "diagnostic" / "summary.md").write_text("# Summary", encoding="utf-8")
        public = {
            "id": "job-1", "status": "completed", "topic": "python", "action": "diagnostic_grade",
            "phase": "grading", "message": "完了しました。", "result": {
                "status": "completed", "summary": "診断が終わりました", "resultPath": ".study/python/diagnostic/summary.md",
                "nextAction": "review_curriculum",
            }, "error": None, "waiting": None, "details": None,
        }

        routed = server._public_job(public)

        self.assertEqual(routed["nextUrl"], "/python/curriculum")
        self.assertTrue(routed["canAcceptDiagnostic"])

    def test_server_routes_a_valid_result_file_without_accepting_a_browser_path(self) -> None:
        result_file = self.topic_dir / "diagnostic" / "01-start.md"
        result_file.write_text("# 最初の診断\n", encoding="utf-8")
        routed = server._public_job({
            "id": "job-2", "status": "completed", "topic": "python", "action": "session_start",
            "phase": "preparing", "message": "完了しました。", "result": {
                "status": "completed", "summary": "最初の診断", "resultPath": ".study/python/diagnostic/01-start.md",
                "nextAction": "answer",
            }, "error": None, "waiting": None, "details": None,
        })

        self.assertEqual(routed["nextUrl"], "/python/diagnostic/01-start.md")

        unavailable = server._public_job({
            "id": "job-3", "status": "completed", "topic": "python", "action": "session_start",
            "phase": "preparing", "message": "完了しました。", "result": {
                "status": "completed", "summary": "存在しないファイル", "resultPath": ".study/python/diagnostic/missing.md",
                "nextAction": "answer",
            }, "error": None, "waiting": None, "details": None,
        })

        # The untrusted missing path is never linked; the server selects the
        # real next diagnostic instead.
        self.assertEqual(unavailable["nextUrl"], "/python/diagnostic/01-start.md")

    def test_lesson_retry_or_continue_uses_only_a_completed_server_job_target(self) -> None:
        manager = _CompletedLessonManager()
        server.app.config["JOB_MANAGER"] = manager
        action, topic, payload = server._validated_job_request({
            "action": "lesson_grade", "data": {"followupJobId": "lesson-source", "resolution": "retry"},
        })

        self.assertEqual((action, topic), ("lesson_grade", "python"))
        self.assertEqual(payload, {
            "target": {"kind": "lessons", "name": "03-functions.md"},
            "feedback": {"tags": ["境界値"], "note": "式を確認"},
            "resolution": "retry",
            "_lessonResolutionSource": "lesson-source",
        })
        with self.assertRaises(ValueError):
            server._validated_job_request({"action": "lesson_grade", "data": {"followupJobId": "lesson-source", "resolution": "continue"}})
        local_manager = JobManager(project_root=self.root.parent, client_factory=_IdleClient)
        self.addCleanup(local_manager.close)
        retry_prompt = local_manager._prompt_for(Job("retry", "lesson_grade", "python", payload))
        continue_prompt = local_manager._prompt_for(Job("continue", "lesson_grade", "python", {**payload, "resolution": "continue"}))
        self.assertIn("異なる新しい課題を生成", retry_prompt)
        self.assertIn("次の未完了項目へ進む", continue_prompt)
        public = server._public_job({
            "id": "lesson-source", "status": "completed", "topic": "python", "action": "lesson_grade",
            "phase": "grading", "message": "完了しました。", "result": {
                "status": "completed", "summary": "採点済み", "resultPath": None, "nextAction": "retry_or_continue",
            }, "error": None, "waiting": None, "details": None,
        })
        self.assertEqual(public["lessonResolution"], {"sourceJobId": "lesson-source", "choices": ["retry", "continue"]})

    def test_codex_prompt_forbids_nested_runtime_tools_and_keeps_quality_paths_in_turn(self) -> None:
        manager = JobManager(project_root=self.root.parent, client_factory=_IdleClient)
        self.addCleanup(manager.close)
        prompt = manager._prompt_for(Job("prompt", "curriculum_accept", "python", {}))

        self.assertIn("外部ツール、MCP、サブエージェント、ネストした Codex", prompt)
        self.assertIn("同じ turn 内", prompt)
        self.assertIn("Generator、Critic、FB-Critic", prompt)

    def test_codex_prompt_requires_one_simple_read_command_per_approval_request(self) -> None:
        manager = JobManager(project_root=self.root.parent, client_factory=_IdleClient)
        self.addCleanup(manager.close)
        prompt = manager._prompt_for(Job("prompt", "lesson_grade", "python", {}))

        self.assertIn("1回の要求につき1つの承認済み読取コマンドだけ", prompt)
        self.assertIn("&&、パイプ、リダイレクト、複合シェルは禁止", prompt)
        self.assertIn("rg --filesを対象ごとに別々", prompt)
        self.assertIn("catまたはsed -nをファイルごとに別々", prompt)

    def test_codex_prompt_requires_apply_patch_as_the_only_markdown_write_mechanism(self) -> None:
        manager = JobManager(project_root=self.root.parent, client_factory=_IdleClient)
        self.addCleanup(manager.close)

        prompt = manager._prompt_for(Job("prompt", "lesson_grade", "python", {}))

        self.assertIn("Markdown の更新は Codex 標準の apply_patch ツールだけを使ってください", prompt)
        self.assertIn("perl、sed -i、python、シェルリダイレクトなどによる書き込みは禁止", prompt)
        self.assertIn("1回の要求で project root 内の .study/<topic> にある必要なファイルだけを変更", prompt)
        self.assertIn("承認後に cat で確認", prompt)

    def test_lesson_resolution_reservation_is_released_when_enqueue_fails_then_committed_once(self) -> None:
        manager = _ReservationRouteManager()
        server.app.config["JOB_MANAGER"] = manager
        payload = {"action": "lesson_grade", "data": {"followupJobId": "lesson-source", "resolution": "retry"}}

        blocked = self.client.post("/api/jobs", json=payload, headers=self._headers())

        self.assertEqual(blocked.status_code, 400)
        self.assertFalse(manager.reserved)
        self.assertFalse(manager.consumed)
        manager.fail_create = False
        accepted = self.client.post("/api/jobs", json=payload, headers=self._headers())
        repeated = self.client.post("/api/jobs", json=payload, headers=self._headers())

        self.assertEqual(accepted.status_code, 202)
        self.assertTrue(manager.consumed)
        self.assertEqual(repeated.status_code, 400)


if __name__ == "__main__":
    unittest.main()
