"""A small, stdlib-only JSONL client for Codex App Server 0.144.3.

The browser never speaks this protocol.  This adapter validates the one local
integration surface and keeps stderr private so only safe, server-owned job
state reaches the UI.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Hashable, TextIO


class AppServerError(RuntimeError):
    """A local App Server request could not be completed safely."""


@dataclass(frozen=True)
class AppServerStatus:
    available: bool
    authenticated: bool
    study_loop_skill_available: bool
    message: str
    skill_path: str | None = None
    recovery: str | None = None
    skill_name: str | None = None


NotificationHandler = Callable[[dict[str, Any]], None]
RequestHandler = Callable[[dict[str, Any]], None]
RequestId = str | int

FINAL_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "summary", "resultPath", "nextAction"],
    "properties": {
        "status": {"type": "string", "enum": ["completed"]},
        "summary": {"type": "string"},
        "resultPath": {"type": ["string", "null"]},
        "nextAction": {
            "type": ["string", "null"],
            "enum": ["answer", "review_curriculum", "retry_or_continue", "done", None],
        },
    },
}


class CodexAppServerClient:
    """A lazily-started, bidirectional JSONL connection.

    The exact message shapes below are derived from codex-cli 0.144.3's
    generated schema.  It can be injected with a fake Popen process for tests.
    """

    def __init__(
        self,
        *,
        study_loop_skill_root: Path,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        command: tuple[str, ...] = ("codex", "app-server", "--stdio"),
    ) -> None:
        self.study_loop_skill_root = study_loop_skill_root.resolve()
        self._popen_factory = popen_factory
        self._command = command
        self._process: Any | None = None
        self._reader: threading.Thread | None = None
        self._stderr_reader: threading.Thread | None = None
        self._stderr_tail: deque[str] = deque(maxlen=64)
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._next_id = 1
        self._responses: dict[RequestId, dict[str, Any]] = {}
        self._notification_handler: NotificationHandler | None = None
        self._request_handler: RequestHandler | None = None
        self._crash_message: str | None = None
        self._status: AppServerStatus | None = None
        self._skill_path: str | None = None
        self._skill_name: str | None = None
        self._closing = False
        self._project_root: Path | None = None
        self._mcp_server_names: tuple[str, ...] = ()
        self._approved_executables = self._resolve_approved_executables()
        self._apply_patch_launcher: Path | None = None

    @property
    def crashed(self) -> bool:
        return self._crash_message is not None

    @property
    def status(self) -> AppServerStatus | None:
        return self._status

    @property
    def skill_path(self) -> str | None:
        return self._skill_path

    @property
    def skill_name(self) -> str | None:
        return self._skill_name

    @property
    def apply_patch_launcher(self) -> Path | None:
        """The verified launcher placed in this turn's fixed PATH, if any."""
        return self._apply_patch_launcher

    def set_handlers(
        self,
        *,
        on_notification: NotificationHandler | None = None,
        on_request: RequestHandler | None = None,
    ) -> None:
        self._notification_handler = on_notification
        self._request_handler = on_request

    def connect(self, *, project_root: Path | None = None) -> AppServerStatus:
        """Spawn, initialize, and discover the enabled canonical Study Loop skill."""
        root = (project_root or Path.cwd()).resolve()
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                if self._status is None:
                    raise AppServerError("Codex App Server の初期化が完了していません。")
                if self._project_root != root:
                    raise AppServerError("Codex App Server のプロジェクト root が一致しません。")
                return self._status
            self._responses.clear()
            self._stderr_tail.clear()
            self._crash_message = None
            self._status = None
            self._skill_path = None
            self._skill_name = None
            self._mcp_server_names = ()
            self._closing = False
            self._project_root = root
            try:
                self._process = self._popen_factory(
                    list(self._command),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                )
                if self._process.stdin is None or self._process.stdout is None:
                    raise AppServerError("Codex App Server の入出力を開けませんでした。")
                self._reader = threading.Thread(target=self._read_loop, name="study-loop-codex-jsonl", daemon=True)
                self._reader.start()
                if self._process.stderr is not None:
                    self._stderr_reader = threading.Thread(target=self._drain_stderr, name="study-loop-codex-stderr", daemon=True)
                    self._stderr_reader.start()
            except FileNotFoundError as exc:
                self._process = None
                raise AppServerError("Codex が見つかりません。Codex をインストールしてください。") from exc
            except (OSError, AppServerError) as exc:
                self._close_process_locked()
                raise AppServerError("Codex App Server を起動できませんでした。") from exc

        try:
            self.request(
                "initialize",
                {
                    "clientInfo": {"name": "study-loop", "title": "Study Loop Learning UI", "version": "1.0"},
                    "capabilities": {"experimentalApi": True},
                },
            )
            self.notify("initialized", {})
            account = self.request("account/read", {})
            config_result = self.request("config/read", {"cwd": str(root), "includeLayers": False})
            self._mcp_server_names = self._configured_mcp_server_names(config_result)
            self.request("skills/extraRoots/set", {"extraRoots": [str(self.study_loop_skill_root)]})
            skills_result = self.request("skills/list", {"cwds": [str(root)], "forceReload": True})
        except AppServerError:
            self.close()
            raise

        authenticated = self._account_authenticated(account)
        discovered_skill = self._discover_study_loop_skill(skills_result, root, self.study_loop_skill_root)
        if discovered_skill is not None:
            self._skill_name, self._skill_path = discovered_skill
        found = discovered_skill is not None
        if not authenticated:
            message = "Codex にログインしていません。`codex login` を実行してください。"
            recovery = "codex login"
        elif not found:
            message = "Study Loop スキルを検出できません。スキルを再読み込みしてからもう一度試してください。"
            recovery = "skills_reload"
        else:
            message = "Codex を利用できます。"
            recovery = None
        self._status = AppServerStatus(
            True,
            authenticated,
            found,
            message,
            skill_path=self._skill_path,
            skill_name=self._skill_name,
            recovery=recovery,
        )
        return self._status

    def restart(self, *, project_root: Path | None = None) -> AppServerStatus:
        """The next job may recover from an EOF/crash with a new process."""
        self.close()
        return self.connect(project_root=project_root or self._project_root)

    def request(self, method: str, params: dict[str, Any], timeout: float = 20.0) -> dict[str, Any]:
        with self._condition:
            if self._process is None or self._process.poll() is not None:
                raise AppServerError(self._crash_message or "Codex App Server が停止しています。")
            request_id: RequestId = self._next_id
            self._next_id += 1
            self._write({"method": method, "id": request_id, "params": params})
            deadline = time.monotonic() + timeout
            while request_id not in self._responses:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AppServerError(f"Codex App Server が {method} に応答しませんでした。")
                if self._crash_message:
                    raise AppServerError(self._crash_message)
                self._condition.wait(remaining)
            message = self._responses.pop(request_id)
        if "error" in message:
            error = message["error"]
            detail = error.get("message") if isinstance(error, dict) else None
            raise AppServerError(f"Codex CLI 0.144.3 互換性エラー: {detail or 'unknown error'}")
        result = message.get("result", {})
        return result if isinstance(result, dict) else {}

    def notify(self, method: str, params: dict[str, Any]) -> None:
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                raise AppServerError(self._crash_message or "Codex App Server が停止しています。")
            self._write({"method": method, "params": params})

    def start_turn(self, *, prompt: str, project_root: Path) -> tuple[str, str]:
        """Start a fresh ephemeral, project-scoped Study Loop turn."""
        root = project_root.resolve()
        if self._project_root != root or not self._skill_path or not self._skill_name:
            raise AppServerError("Codex App Server のスキル検出が完了していません。")
        if not self._approved_executables:
            raise AppServerError("Codex の安全な読取コマンドを解決できませんでした。")
        thread_result = self.request(
            "thread/start",
            {
                "ephemeral": True,
                "cwd": str(root),
                "runtimeWorkspaceRoots": [str(root)],
                "sandbox": "workspace-write",
                "approvalPolicy": "on-request",
                "config": self._thread_config_override(),
            },
        )
        thread = thread_result.get("thread", {})
        thread_id = thread.get("id") if isinstance(thread, dict) else None
        if not isinstance(thread_id, str) or not thread_id:
            raise AppServerError("Codex がスレッド ID を返しませんでした。")
        turn_result = self.request(
            "turn/start",
            {
                "threadId": thread_id,
                "input": [
                    {"type": "skill", "name": self._skill_name, "path": self._skill_path},
                    {"type": "text", "text": prompt},
                ],
                "cwd": str(root),
                "sandboxPolicy": {"type": "workspaceWrite", "writableRoots": [str(root)], "networkAccess": False},
                "approvalPolicy": "on-request",
                "outputSchema": FINAL_OUTPUT_SCHEMA,
            },
        )
        turn = turn_result.get("turn", {})
        turn_id = turn.get("id") if isinstance(turn, dict) else None
        if not isinstance(turn_id, str) or not turn_id:
            raise AppServerError("Codex がターン ID を返しませんでした。")
        return thread_id, turn_id

    @staticmethod
    def _configured_mcp_server_names(config_result: dict[str, Any]) -> tuple[str, ...]:
        """Return only well-formed configured MCP names for a per-turn disable."""
        config = config_result.get("config")
        if not isinstance(config, dict) or not isinstance(config_result.get("origins"), dict):
            raise AppServerError("Codex CLI 0.144.3 互換性エラー: config/read の設定形式が不正です。")
        servers = config.get("mcp_servers", {})
        if not isinstance(servers, dict):
            raise AppServerError("Codex CLI 0.144.3 互換性エラー: mcp_servers の設定形式が不正です。")
        names: list[str] = []
        for name, value in servers.items():
            if not isinstance(name, str) or not name or len(name) > 255 or not isinstance(value, dict):
                raise AppServerError("Codex CLI 0.144.3 互換性エラー: mcp_servers の設定形式が不正です。")
            names.append(name)
        return tuple(sorted(names))

    @staticmethod
    def _resolve_approved_executables() -> dict[str, Path]:
        """Freeze read-only executable paths before any untrusted turn starts."""
        # Do not consult the inherited PATH: a project or shell profile may
        # have inserted a same-named executable. These are standard system
        # package locations; the resolved paths are checked again at approval.
        trusted_dirs = ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin")
        trusted_path = os.pathsep.join(trusted_dirs)
        resolved: dict[str, Path] = {}
        for name in ("pwd", "ls", "git", "rg", "sed", "cat", "shasum"):
            value = shutil.which(name, path=trusted_path)
            if value is None:
                continue
            try:
                candidate = Path(value).resolve(strict=True)
            except OSError:
                continue
            if candidate.is_file() and os.access(candidate, os.X_OK):
                resolved[name] = candidate
        return resolved

    @staticmethod
    def _trusted_codex_binaries(*, command: tuple[str, ...] | None = None) -> set[Path]:
        """Resolve Codex only from fixed application and package locations."""
        candidates = [Path("/Applications/ChatGPT.app/Contents/Resources/codex")]
        if command and command and Path(command[0]).is_absolute():
            candidates.append(Path(command[0]))
        trusted_dirs = ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin")
        installed = shutil.which("codex", path=os.pathsep.join(trusted_dirs))
        if installed is not None:
            candidates.append(Path(installed))
        resolved: set[Path] = set()
        for candidate in candidates:
            try:
                canonical = candidate.resolve(strict=True)
            except OSError:
                continue
            if canonical.is_file() and os.access(canonical, os.X_OK):
                resolved.add(canonical)
        return resolved

    @classmethod
    def _resolve_apply_patch_launcher(
        cls,
        *,
        path_env: str | None = None,
        codex_home: Path | None = None,
        trusted_binaries: set[Path] | None = None,
        command: tuple[str, ...] | None = None,
    ) -> Path | None:
        """Return only Codex's exact, transient ``apply_patch`` launcher.

        Codex desktop injects this launcher under its managed ``arg0`` temp
        directory.  The inherited PATH itself is not trustworthy, so every
        part of the launcher chain is checked before its parent is placed in
        the empty per-turn PATH.
        """
        raw = shutil.which("apply_patch", path=path_env if path_env is not None else os.environ.get("PATH"))
        if raw is None:
            return None
        launcher = Path(raw).absolute()
        if launcher.name != "apply_patch" or not launcher.is_file():
            return None
        home_value = codex_home or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        try:
            arg0_root = (home_value / "tmp" / "arg0").resolve(strict=True)
            launcher_parent = launcher.parent.resolve(strict=True)
            target = launcher.resolve(strict=True)
        except OSError:
            return None
        if (
            launcher_parent.parent != arg0_root
            or not re.fullmatch(r"codex-arg0[A-Za-z0-9_-]+", launcher_parent.name)
            or not target.is_file()
            or not os.access(target, os.X_OK)
        ):
            return None
        trusted = trusted_binaries
        if trusted is None:
            trusted = cls._trusted_codex_binaries(command=command)
        try:
            canonical_trusted = {candidate.resolve(strict=True) for candidate in trusted}
        except OSError:
            return None
        return launcher if target in canonical_trusted else None

    def _thread_config_override(self) -> dict[str, Any]:
        """Disable MCP/collaboration and inherit no caller shell environment."""
        path_entries = list(dict.fromkeys(str(path.parent) for path in self._approved_executables.values()))
        # /bin/sh and /bin/zsh are accepted only by their exact absolute paths,
        # but their directory is needed by Codex when it starts its fixed shell.
        for shell in ("/bin/sh", "/bin/zsh"):
            candidate = Path(shell)
            if candidate.is_file() and os.access(candidate, os.X_OK):
                path_entries.append(str(candidate.parent))
        launcher = self._resolve_apply_patch_launcher(command=self._command)
        self._apply_patch_launcher = launcher
        if launcher is not None:
            # This is the only writer exposed in the turn environment.  The
            # JobManager still requires the subsequent file-change approval.
            path_entries.append(str(launcher.parent))
        safe_path = os.pathsep.join(dict.fromkeys(path_entries))
        return {
            "mcp_servers": {name: {"enabled": False} for name in self._mcp_server_names},
            "features": {"multi_agent": False},
            "allow_login_shell": False,
            "shell_environment_policy": {"inherit": "none", "set": {"PATH": safe_path}},
        }

    def interrupt(self, *, thread_id: str, turn_id: str) -> None:
        try:
            self.request("turn/interrupt", {"threadId": thread_id, "turnId": turn_id}, timeout=5)
        except AppServerError:
            pass

    def respond_to_server_request(self, request_id: RequestId, result: dict[str, Any]) -> None:
        with self._lock:
            self._write({"id": request_id, "result": result})

    def respond_to_server_error(self, request_id: RequestId, code: int, message: str) -> None:
        with self._lock:
            self._write({"id": request_id, "error": {"code": code, "message": message}})

    def close(self) -> None:
        with self._lock:
            self._closing = True
            self._close_process_locked()
            self._status = None

    def terminate_for_cancel(self) -> bool:
        """Synchronously stop the peer and prove it is no longer running.

        Cancellation must not release a topic lock while the App Server can
        still own a turn. A failed terminate therefore leaves the process
        reference intact and reports ``False`` to its caller.
        """
        with self._condition:
            self._closing = True
            process = self._process
            if process is None:
                return True
            try:
                stdin: TextIO | None = process.stdin
                if stdin is not None and hasattr(stdin, "close"):
                    stdin.close()
            except (OSError, ValueError):
                pass
            if process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            stopped = process.poll() is not None
            if stopped:
                self._process = None
                self._status = None
                self._condition.notify_all()
            return stopped

    def _close_process_locked(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            stdin: TextIO | None = process.stdin
            if stdin is not None and hasattr(stdin, "close"):
                stdin.close()
        except (OSError, ValueError):
            pass
        if process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass
        # Keep a live peer reachable.  In particular, cancellation callers
        # must not mistake a discarded reference for a confirmed process exit.
        if process.poll() is not None:
            self._process = None
            self._condition.notify_all()

    def _write(self, message: dict[str, Any]) -> None:
        if self._process is None or self._process.stdin is None:
            raise AppServerError("Codex App Server が起動していません。")
        try:
            self._process.stdin.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as exc:
            self._crash_message = "Codex App Server が終了しました。もう一度開始してください。"
            self._condition.notify_all()
            raise AppServerError(self._crash_message) from exc

    def _read_loop(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        stdout: TextIO = process.stdout
        try:
            while True:
                line = stdout.readline()
                if not line:
                    break
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    continue
                request_id = message.get("id")
                if isinstance(request_id, (str, int)) and ("result" in message or "error" in message):
                    with self._condition:
                        self._responses[request_id] = message
                        self._condition.notify_all()
                    continue
                if isinstance(request_id, (str, int)) and "method" in message:
                    if self._request_handler is not None:
                        self._request_handler(message)
                    continue
                if "method" in message and self._notification_handler is not None:
                    self._notification_handler(message)
        finally:
            with self._condition:
                if not self._closing:
                    self._crash_message = "Codex App Server が予期せず終了しました。もう一度開始してください。"
                self._condition.notify_all()

    def _drain_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        try:
            for line in process.stderr:
                self._stderr_tail.append(line.rstrip()[:400])
        except (OSError, ValueError):
            return

    @staticmethod
    def _account_authenticated(account: dict[str, Any]) -> bool:
        # A local/provider-backed runtime can explicitly state that OpenAI
        # authentication is unnecessary, in which case ``account`` is null.
        if account.get("requiresOpenaiAuth") is False:
            return True
        value = account.get("account")
        if not isinstance(value, dict):
            return False
        return value.get("type") not in {None, "logged_out", "none"}

    @staticmethod
    def _discover_study_loop_skill(
        result: dict[str, Any], root: Path, study_loop_skill_root: Path
    ) -> tuple[str, str] | None:
        """Accept one enabled, canonically located Study Loop entry and its actual name."""
        root = root.resolve()
        canonical_path = (study_loop_skill_root / "SKILL.md").resolve()
        if not canonical_path.is_file():
            return None
        entries = result.get("data")
        if not isinstance(entries, list):
            return None
        canonical_matches: list[tuple[str, str]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            cwd = entry.get("cwd")
            if not isinstance(cwd, str) or not cwd:
                continue
            try:
                resolved_cwd = Path(cwd).resolve()
            except (OSError, UnicodeError, ValueError):
                continue
            if resolved_cwd != root:
                continue
            skills = entry.get("skills")
            if not isinstance(skills, list):
                continue
            for skill in skills:
                if not isinstance(skill, dict):
                    continue
                name = skill.get("name")
                if not isinstance(name, str):
                    continue
                is_bare_study_loop = name == "study-loop"
                is_namespaced_study_loop = (
                    ":" in name
                    and all(part for part in name.split(":"))
                    and name.rsplit(":", 1)[-1] == "study-loop"
                )
                if not (is_bare_study_loop or is_namespaced_study_loop):
                    continue
                path = skill.get("path")
                if skill.get("enabled") is True and isinstance(path, str) and Path(path).resolve() == canonical_path:
                    canonical_matches.append((name, str(canonical_path)))
        if len(canonical_matches) != 1:
            return None
        return canonical_matches[0]
