"""Focused P2 protocol tests for the Codex App Server client."""

from __future__ import annotations

import io
import json
import queue
import sys
import tempfile
import threading
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_app_server import CodexAppServerClient  # type: ignore[import-not-found]
from protocol_fixture_validation import validate_jsonrpc_fixture  # type: ignore[import-not-found]


class _Stdout:
    def __init__(self) -> None:
        self.lines: queue.Queue[str] = queue.Queue()

    def readline(self) -> str:
        return self.lines.get()


class _ProtocolServer:
    """Small JSONL peer with injectable account and skills/list data."""

    def __init__(self, *, account: dict[str, object], skills: list[dict[str, object]]) -> None:
        self.account = account
        self.skills = skills
        self.stdin = self
        self.stdout = _Stdout()
        self.stderr = io.StringIO()
        self.returncode: int | None = None
        self.messages: list[dict[str, object]] = []
        self.responses: dict[str, dict[str, object]] = {}
        self.emitted: list[dict[str, object]] = []

    def write(self, raw: str) -> int:
        message = json.loads(raw)
        self.messages.append(message)
        if "id" not in message:
            return len(raw)
        method = message["method"]
        if method == "initialize":
            result: dict[str, object] = {
                "codexHome": "/tmp/codex",
                "platformFamily": "unix",
                "platformOs": "linux",
                "userAgent": "study-loop-test",
            }
        elif method == "account/read":
            result = self.account
        elif method == "config/read":
            result = {"config": {"mcp_servers": {}}, "origins": {}}
        elif method == "skills/list":
            result = {"data": [{"cwd": message["params"]["cwds"][0], "errors": [], "skills": self.skills}]}
        else:
            result = {}
        self.responses[str(method)] = result
        reply = {"id": message["id"], "result": result}
        self.emitted.append(reply)
        self.stdout.lines.put(json.dumps(reply) + "\n")
        return len(raw)

    def flush(self) -> None:
        return None

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = 0
        self.stdout.lines.put("")

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode or 0


class _StubbornProtocolServer(_ProtocolServer):
    """A peer whose terminate call returns without actually stopping."""

    def terminate(self) -> None:
        return None


class ClientProtocolP2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project_root = Path(self.tmp.name, "project")
        self.project_root.mkdir()
        self.skill_root = Path(self.tmp.name, "configured-study-loop")
        self.skill_root.mkdir()
        self.canonical_skill = self.skill_root / "SKILL.md"
        self.canonical_skill.write_text("# Study Loop\n", encoding="utf-8")

    def _connect(self, *, account: dict[str, object], skills: list[dict[str, object]]):
        peer = _ProtocolServer(account=account, skills=skills)
        client = CodexAppServerClient(
            study_loop_skill_root=self.skill_root,
            popen_factory=lambda *args, **kwargs: peer,
        )
        self.addCleanup(client.close)
        status = client.connect(project_root=self.project_root)
        validate_jsonrpc_fixture(peer.messages, peer.responses, peer.emitted)
        return status

    def _study_loop_skill(self) -> dict[str, object]:
        return {
            "name": "study-loop",
            "description": "Evidence-based learning coach.",
            "enabled": True,
            "path": str(self.canonical_skill),
            "scope": "repo",
        }

    def test_account_null_is_usable_when_openai_auth_is_not_required(self) -> None:
        status = self._connect(
            account={"account": None, "requiresOpenaiAuth": False},
            skills=[self._study_loop_skill()],
        )

        self.assertTrue(status.available)
        self.assertTrue(status.authenticated)
        self.assertTrue(status.study_loop_skill_available)
        self.assertIsNone(status.recovery)

    def test_malformed_mcp_config_is_a_compatibility_error(self) -> None:
        peer = _ProtocolServer(
            account={"account": None, "requiresOpenaiAuth": False},
            skills=[self._study_loop_skill()],
        )
        original_write = peer.write

        def malformed_config(raw: str) -> int:
            message = json.loads(raw)
            if message.get("method") == "config/read":
                peer.messages.append(message)
                result = {"config": {"mcp_servers": ["not-a-map"]}, "origins": {}}
                peer.responses["config/read"] = result
                peer.emitted.append({"id": message["id"], "result": result})
                peer.stdout.lines.put(json.dumps({"id": message["id"], "result": result}) + "\n")
                return len(raw)
            return original_write(raw)

        peer.write = malformed_config  # type: ignore[method-assign]
        client = CodexAppServerClient(study_loop_skill_root=self.skill_root, popen_factory=lambda *args, **kwargs: peer)
        self.addCleanup(client.close)
        with self.assertRaisesRegex(Exception, "互換性エラー"):
            client.connect(project_root=self.project_root)

    def test_account_null_requires_login_when_openai_auth_is_required(self) -> None:
        status = self._connect(
            account={"account": None, "requiresOpenaiAuth": True},
            skills=[self._study_loop_skill()],
        )

        self.assertFalse(status.authenticated)
        self.assertEqual(status.recovery, "codex login")

    def test_terminate_for_cancel_waits_for_process_exit_and_reports_verified_stop(self) -> None:
        peer = _ProtocolServer(
            account={"account": None, "requiresOpenaiAuth": False},
            skills=[self._study_loop_skill()],
        )
        client = CodexAppServerClient(
            study_loop_skill_root=self.skill_root,
            popen_factory=lambda *args, **kwargs: peer,
        )
        self.addCleanup(client.close)
        client.connect(project_root=self.project_root)

        self.assertTrue(client.terminate_for_cancel())
        self.assertEqual(peer.poll(), 0)

    def test_terminate_for_cancel_returns_false_when_poll_still_reports_running(self) -> None:
        peer = _StubbornProtocolServer(
            account={"account": None, "requiresOpenaiAuth": False},
            skills=[self._study_loop_skill()],
        )
        client = CodexAppServerClient(
            study_loop_skill_root=self.skill_root,
            popen_factory=lambda *args, **kwargs: peer,
        )
        self.addCleanup(client.close)
        client.connect(project_root=self.project_root)

        self.assertFalse(client.terminate_for_cancel())
        self.assertIsNone(peer.poll())

    def test_close_keeps_a_stubborn_peer_for_a_later_cancel_attempt(self) -> None:
        peer = _StubbornProtocolServer(
            account={"account": None, "requiresOpenaiAuth": False},
            skills=[self._study_loop_skill()],
        )
        client = CodexAppServerClient(
            study_loop_skill_root=self.skill_root,
            popen_factory=lambda *args, **kwargs: peer,
        )
        client.connect(project_root=self.project_root)

        client.close()

        self.assertIsNone(peer.poll())
        self.assertFalse(client.terminate_for_cancel())
        client.close()  # A second close must be safe while the peer is still live.
        self.assertIsNone(peer.poll())

    def test_skill_discovery_counts_only_enabled_canonical_configured_skill_files(self) -> None:
        wrong_root = Path(self.tmp.name, "same-name-wrong")
        wrong_root.mkdir()
        wrong_skill = wrong_root / "SKILL.md"
        wrong_skill.write_text("# Impostor\n", encoding="utf-8")

        accepted = CodexAppServerClient._discover_study_loop_skill(
            {"data": [{"cwd": str(self.project_root), "errors": [], "skills": [
                self._study_loop_skill(),
            ]}]},
            self.project_root,
            self.skill_root,
        )
        only_wrong = CodexAppServerClient._discover_study_loop_skill(
            {"data": [{"cwd": str(self.project_root), "errors": [], "skills": [
                {**self._study_loop_skill(), "path": str(wrong_skill)},
            ]}]},
            self.project_root,
            self.skill_root,
        )
        canonical_with_disabled_impostor = CodexAppServerClient._discover_study_loop_skill(
            {"data": [{"cwd": str(self.project_root), "errors": [], "skills": [
                self._study_loop_skill(),
                {**self._study_loop_skill(), "enabled": False, "path": str(wrong_skill)},
            ]}]},
            self.project_root,
            self.skill_root,
        )
        duplicate_canonical = CodexAppServerClient._discover_study_loop_skill(
            {"data": [{"cwd": str(self.project_root), "errors": [], "skills": [
                self._study_loop_skill(),
                self._study_loop_skill(),
            ]}]},
            self.project_root,
            self.skill_root,
        )
        namespaced_canonical = CodexAppServerClient._discover_study_loop_skill(
            {"data": [{"cwd": str(self.project_root), "errors": [], "skills": [
                {**self._study_loop_skill(), "name": "plugin:study-loop"},
            ]}]},
            self.project_root,
            self.skill_root,
        )
        wrong_namespaced_suffix = CodexAppServerClient._discover_study_loop_skill(
            {"data": [{"cwd": str(self.project_root), "errors": [], "skills": [
                {**self._study_loop_skill(), "name": "study-loop:other"},
            ]}]},
            self.project_root,
            self.skill_root,
        )

        self.assertEqual(accepted, ("study-loop", str(self.canonical_skill.resolve())))
        self.assertIsNone(only_wrong)
        self.assertEqual(canonical_with_disabled_impostor, ("study-loop", str(self.canonical_skill.resolve())))
        self.assertIsNone(duplicate_canonical)
        self.assertEqual(namespaced_canonical, ("plugin:study-loop", str(self.canonical_skill.resolve())))
        self.assertIsNone(wrong_namespaced_suffix)

    def test_skill_discovery_rejects_entries_without_a_nonempty_string_cwd(self) -> None:
        canonical_namespaced_skill = {
            **self._study_loop_skill(),
            "name": "study-loop:study-loop",
            "path": str(self.canonical_skill),
        }
        root = Path.cwd()
        missing_cwd = CodexAppServerClient._discover_study_loop_skill(
            {"data": [{"errors": [], "skills": [canonical_namespaced_skill]}]},
            root,
            self.skill_root,
        )
        empty_cwd = CodexAppServerClient._discover_study_loop_skill(
            {"data": [{"cwd": "", "errors": [], "skills": [canonical_namespaced_skill]}]},
            root,
            self.skill_root,
        )
        non_string_cwd = CodexAppServerClient._discover_study_loop_skill(
            {"data": [{"cwd": 0, "errors": [], "skills": [canonical_namespaced_skill]}]},
            root,
            self.skill_root,
        )
        valid_namespaced_cwd = CodexAppServerClient._discover_study_loop_skill(
            {"data": [{"cwd": str(root), "errors": [], "skills": [canonical_namespaced_skill]}]},
            root,
            self.skill_root,
        )

        self.assertIsNone(missing_cwd)
        self.assertIsNone(empty_cwd)
        self.assertIsNone(non_string_cwd)
        self.assertEqual(valid_namespaced_cwd, ("study-loop:study-loop", str(self.canonical_skill.resolve())))

    def test_skill_discovery_ignores_malformed_string_cwds(self) -> None:
        canonical_namespaced_skill = {
            **self._study_loop_skill(),
            "name": "study-loop:study-loop",
            "path": str(self.canonical_skill),
        }
        root = Path.cwd()
        null_cwd = CodexAppServerClient._discover_study_loop_skill(
            {"data": [{"cwd": "\x00", "errors": [], "skills": [canonical_namespaced_skill]}]},
            root,
            self.skill_root,
        )
        surrogate_cwd = CodexAppServerClient._discover_study_loop_skill(
            {"data": [{"cwd": "\udcff", "errors": [], "skills": [canonical_namespaced_skill]}]},
            root,
            self.skill_root,
        )
        valid_namespaced_cwd = CodexAppServerClient._discover_study_loop_skill(
            {"data": [{"cwd": str(root), "errors": [], "skills": [canonical_namespaced_skill]}]},
            root,
            self.skill_root,
        )

        self.assertIsNone(null_cwd)
        self.assertIsNone(surrogate_cwd)
        self.assertEqual(valid_namespaced_cwd, ("study-loop:study-loop", str(self.canonical_skill.resolve())))


if __name__ == "__main__":
    unittest.main()
