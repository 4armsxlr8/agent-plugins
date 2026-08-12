"""Red-first tests for Study Loop's local Codex App Server integration."""

from __future__ import annotations

import io
import json
import queue
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_app_server import CodexAppServerClient  # type: ignore[import-not-found]
from jobs import ALLOWED_ACTIONS, JobManager  # type: ignore[import-not-found]
import protocol_fixture_validation
from protocol_fixture_validation import SCHEMA_ROOT, validate_jsonrpc_fixture


class _FakeStdout:
    def __init__(self) -> None:
        self.lines: queue.Queue[str] = queue.Queue()

    def readline(self) -> str:
        return self.lines.get()


class FakeAppServer:
    """A JSONL harness that lets tests assert the client handshake and turn flow."""

    def __init__(self, *, emit_server_request: bool = False) -> None:
        self.stdout = _FakeStdout()
        self.stdin = self
        self.stderr = io.StringIO()
        self.returncode: int | None = None
        self.emit_server_request = emit_server_request
        self.messages: list[dict[str, object]] = []
        self.responses: dict[str, dict[str, object]] = {}
        self.emitted: list[dict[str, object]] = []

    def write(self, raw: str) -> int:
        message = json.loads(raw)
        self.messages.append(message)
        method = message.get("method")
        if method is None:
            if message.get("id") == "approval-1":
                self.emit({"method": "serverRequest/resolved", "params": {"requestId": "approval-1", "threadId": "thr_fake"}})
            return len(raw)
        if "id" not in message:
            return len(raw)
        result: dict[str, object]
        if method == "initialize":
            result = {"codexHome": "/tmp/codex", "platformFamily": "unix", "platformOs": "linux", "userAgent": "study-loop-test"}
        elif method == "account/read":
            result = {"account": {"type": "chatgpt", "email": "test@example.invalid", "planType": "plus"}, "requiresOpenaiAuth": True}
        elif method == "config/read":
            result = {"config": {"mcp_servers": {}}, "origins": {}}
        elif method == "skills/list":
            result = {"data": [{"cwd": message["params"]["cwds"][0], "errors": [], "skills": [{
                "name": "study-loop", "enabled": True, "path": str(SCRIPTS.parent / "SKILL.md"), "description": "x", "scope": "repo",
            }]}]}
        elif method == "thread/start":
            result = {
                "thread": {
                    "id": "thr_fake", "cliVersion": "0.144.3", "createdAt": 0, "updatedAt": 0,
                    "cwd": "/tmp/project", "ephemeral": True, "modelProvider": "openai", "preview": "",
                    "sessionId": "session_fake", "source": "appServer", "status": {"type": "idle"}, "turns": [],
                },
                "approvalPolicy": "on-request", "approvalsReviewer": "user", "cwd": "/tmp/project",
                "model": "gpt-5", "modelProvider": "openai",
                "sandbox": {"type": "workspaceWrite", "writableRoots": ["/tmp/project"], "networkAccess": False},
            }
        elif method == "turn/start":
            result = {"turn": {"id": "turn_fake", "items": [], "status": "inProgress"}}
        elif method == "turn/interrupt":
            result = {}
        else:
            result = {}
        self.responses[str(method)] = result
        self.emit({"id": message["id"], "result": result})
        if method == "turn/start":
            if self.emit_server_request:
                threading.Timer(0.005, lambda: self.emit({
                    "id": "approval-1", "method": "item/commandExecution/requestApproval", "params": {
                        "threadId": "thr_fake", "turnId": "turn_fake", "itemId": "item_fake",
                        "command": "pwd", "cwd": "/tmp/project", "reason": "作業場所の確認",
                        "startedAtMs": 0,
                        "availableDecisions": ["accept", "decline", "cancel"],
                    },
                })).start()
            threading.Timer(0.01, lambda: self.emit({
                "method": "item/agentMessage/delta",
                "params": {"threadId": "thr_fake", "turnId": "turn_fake", "itemId": "item_fake", "delta": '{"status":"completed","summary":"完了","resultPath":null,"nextAction":"done"}'},
            })).start()
            threading.Timer(0.02, lambda: self.emit({"method": "turn/completed", "params": {"threadId": "thr_fake", "turn": {"id": "turn_fake", "items": [], "status": "completed"}}})).start()
        if method == "turn/interrupt":
            threading.Timer(0.01, lambda: self.emit({"method": "turn/completed", "params": {"threadId": "thr_fake", "turn": {"id": "turn_fake", "items": [], "status": "interrupted"}}})).start()
        return len(raw)

    def flush(self) -> None:
        return None

    def emit(self, message: dict[str, object]) -> None:
        self.emitted.append(message)
        self.stdout.lines.put(json.dumps(message) + "\n")

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = 0
        self.stdout.lines.put("")

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode or 0


class CodexClientTests(unittest.TestCase):
    def test_fixture_validator_rejects_unknown_client_notification(self) -> None:
        with self.assertRaises(AssertionError):
            validate_jsonrpc_fixture(
                [{"method": "not/a/client/notification", "params": {}}], {}, []
            )

    def test_fixture_validator_fallback_checks_nested_protocol_shapes(self) -> None:
        original_schema = protocol_fixture_validation._schema
        protocol_fixture_validation._schema = lambda _path: None
        self.addCleanup(setattr, protocol_fixture_validation, "_schema", original_schema)

        valid_responses = {
            "initialize": {"codexHome": "/tmp/codex", "platformFamily": "unix", "platformOs": "linux", "userAgent": "test"},
            "account/read": {"account": {"type": "chatgpt", "email": "a@example.invalid", "planType": "plus"}, "requiresOpenaiAuth": True},
            "config/read": {"config": {"mcp_servers": {}}, "origins": {}},
            "skills/list": {"data": [{"cwd": "/tmp/project", "errors": [], "skills": [{"name": "study-loop", "description": "test", "enabled": True, "path": "/tmp/SKILL.md", "scope": "repo"}]}]},
            "thread/start": {"thread": {"id": "thr", "status": {"type": "idle"}, "turns": []}, "approvalPolicy": "on-request", "approvalsReviewer": "user", "cwd": "/tmp/project", "model": "gpt-5", "modelProvider": "openai", "sandbox": {"type": "workspaceWrite", "writableRoots": ["/tmp/project"], "networkAccess": False}},
            "turn/start": {"turn": {"id": "turn", "items": [], "status": "inProgress"}},
            "turn/interrupt": {},
        }
        valid_messages = [
            {"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "study-loop", "version": "test"}}},
            {"method": "initialized", "params": {}},
        ]
        valid_emitted = [
            {"method": "item/agentMessage/delta", "params": {"threadId": "thr", "turnId": "turn", "itemId": "item", "delta": "text"}},
            {"method": "turn/completed", "params": {"threadId": "thr", "turn": {"id": "turn", "items": [], "status": "completed"}}},
        ]
        validate_jsonrpc_fixture(valid_messages, valid_responses, valid_emitted)

        malformed_cases = [
            ({"initialize": {"codexHome": 7, "platformFamily": "unix", "platformOs": "linux", "userAgent": "test"}}, []),
            ({"account/read": {"account": {"type": "chatgpt", "email": 7, "planType": "plus"}, "requiresOpenaiAuth": True}}, []),
            ({"thread/start": {**valid_responses["thread/start"], "thread": {"id": 7, "status": {"type": "idle"}, "turns": []}}}, []),
            ({"turn/start": {"turn": {"id": "turn", "items": {}, "status": "inProgress"}}}, []),
            ({}, [{"method": "turn/completed", "params": {"threadId": "thr", "turn": {"id": "turn", "items": {}, "status": "completed"}}}]),
        ]
        for responses, emitted in malformed_cases:
            with self.subTest(responses=responses, emitted=emitted), self.assertRaises(AssertionError):
                validate_jsonrpc_fixture(valid_messages, responses, emitted)

    def test_fixture_validator_rejects_malformed_method_payloads_when_schemas_exist(self) -> None:
        if not (SCHEMA_ROOT / "v1/InitializeParams.json").is_file():
            self.skipTest("local generated App Server schemas are unavailable")

        malformed = [{
            "id": 1,
            "method": "initialize",
            "params": {"clientInfo": {"name": 9, "version": "study-loop-test"}},
        }]

        with self.assertRaises(AssertionError):
            validate_jsonrpc_fixture(malformed, {}, [])

    def test_fake_interrupt_reports_a_matching_interrupted_terminal_turn(self) -> None:
        fake = FakeAppServer()
        client = CodexAppServerClient(
            study_loop_skill_root=SCRIPTS.parent,
            popen_factory=lambda *args, **kwargs: fake,
        )
        self.addCleanup(client.close)
        interrupted = threading.Event()

        def notice(message: dict[str, object]) -> None:
            params = message.get("params")
            turn = params.get("turn") if isinstance(params, dict) else None
            if message.get("method") == "turn/completed" and isinstance(turn, dict) and turn.get("status") == "interrupted":
                interrupted.set()

        client.set_handlers(on_notification=notice)
        client.connect(project_root=Path("/tmp/project"))
        thread_id, turn_id = client.start_turn(prompt="固定プロンプト", project_root=Path("/tmp/project"))
        client.interrupt(thread_id=thread_id, turn_id=turn_id)

        self.assertEqual(fake.responses["turn/interrupt"], {})
        self.assertTrue(interrupted.wait(0.5))
        terminal = next(message for message in fake.emitted if message.get("method") == "turn/completed" and message["params"]["turn"]["status"] == "interrupted")
        self.assertEqual(terminal["params"], {"threadId": "thr_fake", "turn": {"id": "turn_fake", "items": [], "status": "interrupted"}})
        validate_jsonrpc_fixture(fake.messages, fake.responses, fake.emitted)

    def test_fake_uses_complete_protocol_shapes_and_resolves_a_server_request(self) -> None:
        fake = FakeAppServer(emit_server_request=True)
        client = CodexAppServerClient(
            study_loop_skill_root=SCRIPTS.parent,
            popen_factory=lambda *args, **kwargs: fake,
        )
        self.addCleanup(client.close)
        request_seen = threading.Event()
        resolved_seen = threading.Event()
        terminal_seen = threading.Event()

        def answer_server_request(message: dict[str, object]) -> None:
            request_seen.set()
            client.respond_to_server_request(message["id"], {"decision": "decline"})

        def notice(message: dict[str, object]) -> None:
            if message.get("method") == "serverRequest/resolved":
                resolved_seen.set()
            if message.get("method") == "turn/completed":
                terminal_seen.set()

        client.set_handlers(on_notification=notice, on_request=answer_server_request)
        client.connect(project_root=Path("/tmp/project"))
        client.start_turn(prompt="固定プロンプト", project_root=Path("/tmp/project"))

        self.assertEqual(set(fake.responses["initialize"]), {"codexHome", "platformFamily", "platformOs", "userAgent"})
        self.assertEqual(fake.responses["account/read"]["account"], {"type": "chatgpt", "email": "test@example.invalid", "planType": "plus"})
        thread = fake.responses["thread/start"]["thread"]
        self.assertTrue({"id", "cliVersion", "createdAt", "updatedAt", "cwd", "ephemeral", "modelProvider", "preview", "sessionId", "source", "status", "turns"} <= set(thread))
        self.assertEqual(thread["status"], {"type": "idle"})
        self.assertEqual(fake.responses["turn/start"]["turn"], {"id": "turn_fake", "items": [], "status": "inProgress"})
        self.assertTrue(request_seen.wait(0.5))
        self.assertTrue(resolved_seen.wait(0.5))
        self.assertTrue(terminal_seen.wait(0.5))
        validate_jsonrpc_fixture(fake.messages, fake.responses, fake.emitted)
        terminal = next(message for message in fake.emitted if message.get("method") == "turn/completed")
        self.assertEqual(terminal["params"]["turn"], {"id": "turn_fake", "items": [], "status": "completed"})

    def test_server_request_response_is_emitted_exactly_once(self) -> None:
        fake = FakeAppServer()
        client = CodexAppServerClient(
            study_loop_skill_root=SCRIPTS.parent,
            popen_factory=lambda *args, **kwargs: fake,
        )
        self.addCleanup(client.close)
        client.connect(project_root=Path("/tmp/project"))

        client.respond_to_server_request("approval-1", {"decision": "accept"})

        replies = [message for message in fake.messages if message.get("id") == "approval-1"]
        self.assertEqual(replies, [{"id": "approval-1", "result": {"decision": "accept"}}])

    def test_client_initializes_with_experimental_skill_setup_and_starts_turn(self) -> None:
        fake = FakeAppServer()
        client = CodexAppServerClient(
            study_loop_skill_root=SCRIPTS.parent,
            popen_factory=lambda *args, **kwargs: fake,
        )
        self.addCleanup(client.close)

        status = client.connect(project_root=Path("/tmp/project"))
        thread_id, turn_id = client.start_turn(
            prompt="固定プロンプト",
            project_root=Path("/tmp/project"),
        )

        self.assertTrue(status.available)
        self.assertEqual((thread_id, turn_id), ("thr_fake", "turn_fake"))
        methods = [m.get("method") for m in fake.messages]
        self.assertEqual(methods[:7], [
            "initialize", "initialized", "account/read", "config/read", "skills/extraRoots/set", "skills/list", "thread/start",
        ])
        initialize = fake.messages[0]
        self.assertTrue(initialize["params"]["capabilities"]["experimentalApi"])  # type: ignore[index]
        turn = next(m for m in fake.messages if m.get("method") == "turn/start")
        self.assertEqual(turn["params"]["cwd"], str(Path("/tmp/project").resolve()))  # type: ignore[index]
        self.assertFalse(turn["params"]["outputSchema"]["additionalProperties"])  # type: ignore[index]

    def test_eof_marks_the_client_crashed_and_a_later_job_restarts_cleanly(self) -> None:
        first = FakeAppServer()
        second = FakeAppServer()
        servers = iter([first, second])
        client = CodexAppServerClient(
            study_loop_skill_root=SCRIPTS.parent,
            popen_factory=lambda *args, **kwargs: next(servers),
        )
        self.addCleanup(client.close)

        client.connect(project_root=Path("/tmp/project"))
        first.stdout.lines.put("")
        deadline = time.monotonic() + 1
        while not client.crashed and time.monotonic() < deadline:
            time.sleep(0.01)
        status = client.restart(project_root=Path("/tmp/project"))

        self.assertTrue(client.crashed is False)
        self.assertTrue(status.available)
        self.assertIn("initialize", [message.get("method") for message in second.messages])


class JobManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.fake = FakeAppServer()
        self.client = CodexAppServerClient(
            study_loop_skill_root=SCRIPTS.parent,
            popen_factory=lambda *args, **kwargs: self.fake,
        )
        self.manager = JobManager(
            project_root=self.root,
            client_factory=lambda: self.client,
        )
        self.addCleanup(self.manager.close)

    def test_only_allowlisted_actions_are_accepted(self) -> None:
        self.assertIn("session_start", ALLOWED_ACTIONS)
        with self.assertRaises(ValueError):
            self.manager.create_job("rm_everything", "python", {})

    def test_duplicate_topic_job_is_rejected_and_completed_job_has_strict_result(self) -> None:
        job = self.manager.create_job("session_start", "python", {
            "topic": "Python", "why": "仕事で使う", "successCriteria": ["関数を書ける", "テストできる"],
            "constraints": "平日30分", "outOfScope": "Web開発", "retentionInterval": "1か月",
            "targetLevel": 3, "timeBudget": "30分 x 10日",
        })
        with self.assertRaises(ValueError):
            self.manager.create_job("session_start", "python", {})

        deadline = time.monotonic() + 2
        while self.manager.get_job(job.id).status not in {"completed", "failed"} and time.monotonic() < deadline:
            time.sleep(0.01)
        done = self.manager.get_job(job.id)
        self.assertEqual(done.status, "completed")
        self.assertEqual(done.result, {
            "status": "completed", "summary": "完了", "resultPath": None, "nextAction": "done",
        })
        self.assertTrue(self.manager.events_after(job.id, 0))


if __name__ == "__main__":
    unittest.main()
