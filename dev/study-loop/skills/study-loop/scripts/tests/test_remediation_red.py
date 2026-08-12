"""Focused red-first regressions for the App Server remediation."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import queue
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from codex_app_server import CodexAppServerClient
from protocol_fixture_validation import validate_jsonrpc_fixture

SERVER_PATH = SCRIPTS / "server.py"
SPEC = importlib.util.spec_from_file_location("study_loop_server_remediation", SERVER_PATH)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


class _Stdout:
    def __init__(self) -> None:
        self.lines: queue.Queue[str] = queue.Queue()

    def readline(self) -> str:
        return self.lines.get()


class Protocol144Harness:
    """Only authentic 0.144.3 response shapes are emitted by this harness."""

    def __init__(self) -> None:
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
            result = {"codexHome": "/tmp/codex", "platformFamily": "unix", "platformOs": "linux", "userAgent": "study-loop-test"}
        elif method == "account/read":
            result = {"account": {"type": "chatgpt", "email": "test@example.invalid", "planType": "plus"}, "requiresOpenaiAuth": True}
        elif method == "config/read":
            result = {"config": {"mcp_servers": {"unsafe-server": {"command": "ignored"}}}, "origins": {}}
        elif method == "skills/list":
            result = {"data": [{
                "cwd": "/tmp/project", "errors": [],
                # Codex App Server returns the plugin-qualified name for the
                # actual canonical Study Loop skill.
                "skills": [{"name": "study-loop:study-loop", "enabled": True, "path": str(SCRIPTS.parent / "SKILL.md"), "description": "x", "scope": "repo"}],
            }]}
        elif method == "thread/start":
            result = {
                "thread": {
                    "id": "thread-144", "cliVersion": "0.144.3", "createdAt": 0, "updatedAt": 0,
                    "cwd": "/tmp/project", "ephemeral": True, "modelProvider": "openai", "preview": "",
                    "sessionId": "session-144", "source": "appServer", "status": {"type": "idle"}, "turns": [],
                },
                "approvalPolicy": "on-request", "approvalsReviewer": "user", "cwd": "/tmp/project",
                "model": "gpt-5", "modelProvider": "openai",
                "sandbox": {"type": "workspaceWrite", "writableRoots": ["/tmp/project"], "networkAccess": False},
            }
        elif method == "turn/start":
            result = {"turn": {"id": "turn-144", "items": [], "status": "inProgress"}}
        else:
            result = {}
        self.responses[str(method)] = result
        response = {"id": message["id"], "result": result}
        self.emitted.append(response)
        self.stdout.lines.put(json.dumps(response) + "\n")
        return len(raw)

    def flush(self) -> None:
        return None

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.returncode = 0
        self.stdout.lines.put("")

    def wait(self, timeout=None):
        return 0


class ProtocolRemediationTests(unittest.TestCase):
    def test_144_skill_discovery_and_turn_contract(self) -> None:
        fake = Protocol144Harness()
        client = CodexAppServerClient(study_loop_skill_root=SCRIPTS.parent, popen_factory=lambda *a, **k: fake)
        self.addCleanup(client.close)

        status = client.connect(project_root=Path("/tmp/project"))
        client.start_turn(prompt="fixed", project_root=Path("/tmp/project"))

        self.assertTrue(status.study_loop_skill_available)
        self.assertEqual(status.skill_name, "study-loop:study-loop")
        listed = next(m for m in fake.messages if m.get("method") == "skills/list")
        self.assertEqual(listed["params"], {"cwds": [str(Path("/tmp/project").resolve())], "forceReload": True})  # type: ignore[index]
        config_read = next(m for m in fake.messages if m.get("method") == "config/read")
        self.assertEqual(config_read["params"], {"cwd": str(Path("/tmp/project").resolve()), "includeLayers": False})  # type: ignore[index]
        thread = next(m for m in fake.messages if m.get("method") == "thread/start")
        self.assertTrue(thread["params"]["ephemeral"])  # type: ignore[index]
        path_entries = list(dict.fromkeys(str(path.parent) for path in client._approved_executables.values()))
        for shell in ("/bin/sh", "/bin/zsh"):
            if Path(shell).is_file() and os.access(shell, os.X_OK):
                path_entries.append(str(Path(shell).parent))
        launcher = client._resolve_apply_patch_launcher(command=client._command)
        if launcher is not None:
            path_entries.append(str(launcher.parent))
        expected_config = {
            "mcp_servers": {"unsafe-server": {"enabled": False}},
            "features": {"multi_agent": False},
            "allow_login_shell": False,
            "shell_environment_policy": {"inherit": "none", "set": {"PATH": os.pathsep.join(dict.fromkeys(path_entries))}},
        }
        self.assertEqual(thread["params"]["config"], {  # type: ignore[index]
            **expected_config,
        })
        policy = thread["params"]["config"]["shell_environment_policy"]  # type: ignore[index]
        self.assertEqual(policy["inherit"], "none")
        self.assertEqual(set(policy["set"]), {"PATH"})
        self.assertNotIn("HOME", policy["set"])
        created = fake.responses["thread/start"]["thread"]
        self.assertTrue({"id", "cliVersion", "createdAt", "updatedAt", "cwd", "ephemeral", "modelProvider", "preview", "sessionId", "source", "status", "turns"} <= set(created))
        self.assertEqual(created["status"], {"type": "idle"})
        turn = next(m for m in fake.messages if m.get("method") == "turn/start")
        self.assertEqual(turn["params"]["input"][0], {"type": "skill", "name": "study-loop:study-loop", "path": str(SCRIPTS.parent / "SKILL.md")})  # type: ignore[index]
        schema = turn["params"]["outputSchema"]  # type: ignore[index]
        self.assertFalse(schema["additionalProperties"])  # type: ignore[index]
        validate_jsonrpc_fixture(fake.messages, fake.responses, fake.emitted)


class MarkdownRemediationTests(unittest.TestCase):
    def test_answer_replacement_preserves_literal_backslashes(self) -> None:
        source = "## 回答欄\n\nold\n\n---\n\n## ヒント\ntext\n"
        answer = r"\\1 \\g<name> C:\\work\\code\n```py\nre.sub(r'\\1', x)\n```"
        replaced = server.replace_answer(source, answer)

        self.assertIn(answer, replaced)

    def test_rendered_markdown_strips_active_html_and_keeps_plain_markdown(self) -> None:
        html = server.render_markdown("# Title\n\n[ok](https://example.com) [bad](javascript:alert(1))\n<script>alert(1)</script>\n<span onclick=alert(1)>x</span>")

        self.assertIn("<h1>Title</h1>", html)
        self.assertIn('href="https://example.com"', html)
        self.assertNotIn("script", html.lower())
        self.assertNotIn("onclick", html.lower())
        self.assertNotIn("javascript:", html.lower())
        self.assertNotIn("alert(1)", html.lower())


if __name__ == "__main__":
    unittest.main()
