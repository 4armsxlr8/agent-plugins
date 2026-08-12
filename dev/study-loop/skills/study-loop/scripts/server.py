#!/usr/bin/env python3
"""Study Loop Web UI — local Flask server for viewing and answering study lesson files.

Usage:
    python3 server.py [--port 8765] [--root .study] [--host 127.0.0.1]

Design:
    md ファイルが学習状態のシングルソース。サーバーはジョブ、確認トークン、SSE
    を再起動で失われるメモリ状態としてだけ保持し、表示と回答記入を担う。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

try:
    from flask import (
        Flask,
        Response,
        abort,
        redirect,
        render_template,
        request,
        session,
        jsonify,
        stream_with_context,
        url_for,
    )
    import markdown as md_lib
except ImportError:
    print(
        "ERROR: Flask / Markdown が見つかりません。依存をインストールしてください:\n"
        "  pip install -r requirements.txt\n"
        "（venv 推奨）",
        file=sys.stderr,
    )
    sys.exit(1)

from codex_app_server import AppServerStatus, CodexAppServerClient
from jobs import ALLOWED_ACTIONS, JobManager

SCRIPT_DIR = Path(__file__).resolve().parent
app = Flask(
    __name__,
    template_folder=str(SCRIPT_DIR / "templates"),
    static_folder=str(SCRIPT_DIR / "static"),
)
app.secret_key = os.environ.get("STUDY_LOOP_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    BACKEND=os.environ.get("STUDY_LOOP_BACKEND", "auto"),
    PROJECT_ROOT=None,
    JOB_MANAGER=None,
    CODEX_PATH=None,
    CONFIRMATIONS={},
)
_CONFIRMATIONS_LOCK = threading.RLock()


# A topic's files can be written by a browser submit and a Codex turn at nearly
# the same time. Locks serialize that local session while atomic replace keeps
# each file readable even if the process stops between write operations.
_SESSION_LOCKS: dict[str, threading.RLock] = {}
_SESSION_LOCKS_GUARD = threading.Lock()


def atomic_write(path: Path, content: str) -> None:
    """Durably replace a UTF-8 file using a temporary file in the same directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            # Filesystems without directory fsync still retain the atomic
            # replacement guarantee, so do not turn a successful save into an
            # apparent failure.
            pass
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


@contextmanager
def session_lock(topic_dir: Path) -> Any:
    key = str(topic_dir.resolve())
    with _SESSION_LOCKS_GUARD:
        lock = _SESSION_LOCKS.setdefault(key, threading.RLock())
    with lock:
        yield


@app.after_request
def add_security_headers(response: Any) -> Any:
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
        "form-action 'self'; connect-src 'self'; img-src 'self' data:; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


# ---------- Markdown rendering ----------

MD_EXTENSIONS = [
    "fenced_code",
    "tables",
    "toc",
    "sane_lists",
    "attr_list",
    "md_in_html",
    "pymdownx.tilde",
    "pymdownx.tasklist",
    "pymdownx.superfences",
]
MD_EXTENSION_CONFIGS = {
    "pymdownx.tasklist": {"custom_checkbox": True},
}


def render_markdown(text: str) -> str:
    rendered = md_lib.markdown(
        text,
        extensions=MD_EXTENSIONS,
        extension_configs=MD_EXTENSION_CONFIGS,
        output_format="html5",
    )
    return sanitize_html(rendered)


_SAFE_TAGS = frozenset({
    "a", "article", "blockquote", "br", "code", "dd", "del", "details", "div", "dl", "dt",
    "em", "figcaption", "figure", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "img", "input",
    "kbd", "li", "ol", "p", "pre", "s", "small", "span", "strong", "summary", "sup", "table",
    "tbody", "td", "th", "thead", "tr", "ul",
})
_SAFE_ATTRS = {
    "a": {"href", "title"},
    "code": {"class"}, "div": {"class"}, "input": {"checked", "disabled", "type"},
    "ol": {"start"}, "span": {"class"}, "table": {"class"}, "td": {"align"}, "th": {"align"},
    "pre": {"class"}, "img": {"alt", "src", "title"},
}


def sanitize_html(html: str) -> str:
    """Strip active markup from Markdown output without adding a runtime package."""
    from html.parser import HTMLParser
    from html import escape

    class Sanitizer(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.parts: list[str] = []
            self.open_tags: list[str] = []
            self.blocked_depth = 0

        _BLOCKED_CONTENT_TAGS = frozenset({"script", "style", "iframe", "object", "embed", "svg", "math", "template"})

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            tag = tag.lower()
            if self.blocked_depth:
                if tag in self._BLOCKED_CONTENT_TAGS:
                    self.blocked_depth += 1
                return
            if tag in self._BLOCKED_CONTENT_TAGS:
                self.blocked_depth = 1
                return
            if tag not in _SAFE_TAGS:
                return
            allowed = _SAFE_ATTRS.get(tag, set())
            safe: list[str] = []
            for name, value in attrs:
                name = name.lower()
                if name not in allowed or name.startswith("on") or value is None:
                    continue
                if name in {"href", "src"} and not _safe_url(value):
                    continue
                safe.append(f' {name}="{escape(value, quote=True)}"')
            void = tag in {"br", "hr", "img", "input"}
            self.parts.append(f"<{tag}{''.join(safe)}>")
            if not void:
                self.open_tags.append(tag)

        def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            self.handle_starttag(tag, attrs)
            if tag.lower() in self.open_tags:
                self.handle_endtag(tag)

        def handle_endtag(self, tag: str) -> None:
            tag = tag.lower()
            if self.blocked_depth:
                if tag in self._BLOCKED_CONTENT_TAGS:
                    self.blocked_depth -= 1
                return
            if tag in self.open_tags:
                while self.open_tags:
                    current = self.open_tags.pop()
                    self.parts.append(f"</{current}>")
                    if current == tag:
                        break

        def handle_data(self, data: str) -> None:
            if not self.blocked_depth:
                self.parts.append(escape(data))

    parser = Sanitizer()
    parser.feed(html)
    parser.close()
    return "".join(parser.parts)


def _safe_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    if parsed.scheme.lower() in {"javascript", "data", "vbscript"}:
        return False
    return not parsed.scheme or parsed.scheme.lower() in {"http", "https", "mailto"}


# ---------- Filesystem helpers ----------


def safe_path(root: Path, *parts: str) -> Path:
    """パストラバーサル対策。root の外に出ないことを保証する。"""
    p = (root / Path(*parts)).resolve()
    root_resolved = root.resolve()
    if root_resolved not in p.parents and p != root_resolved:
        abort(403, "path escapes root")
    return p


# ---------- Local-only request security / Codex jobs ----------


def _is_loopback_host(value: str) -> bool:
    if value.startswith("["):
        host = value[1:].split("]", 1)[0]
    elif value.count(":") == 1:
        host = value.rsplit(":", 1)[0]
    else:
        host = value
    host = host.strip("[]").lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def _validate_local_request() -> None:
    """The App Server bridge is intentionally reachable only from this machine."""
    if not _is_loopback_host(request.host):
        abort(403, "Study Loop UI is available only on loopback.")
    origin = request.headers.get("Origin")
    if origin:
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or not _is_loopback_host(parsed.netloc):
            abort(403, "cross-origin request denied")


@app.before_request
def enforce_local_request() -> None:
    _validate_local_request()


def csrf_token() -> str:
    token = session.get("csrf_token")
    if not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def require_csrf() -> None:
    supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
    expected = session.get("csrf_token")
    if not isinstance(expected, str) or not isinstance(supplied, str) or not secrets.compare_digest(expected, supplied):
        abort(403, "CSRF validation failed")


def _project_root() -> Path:
    configured = app.config.get("PROJECT_ROOT")
    if configured:
        return Path(configured).resolve()
    return Path(app.config["ROOT"]).resolve().parent


def _backend() -> str:
    value = str(app.config.get("BACKEND", "auto"))
    return value if value in {"auto", "codex", "manual"} else "auto"


def _codex_path() -> str | None:
    configured = app.config.get("CODEX_PATH")
    return str(configured) if configured else shutil.which("codex")


def _job_manager() -> JobManager:
    existing = app.config.get("JOB_MANAGER")
    if existing is not None:
        return existing
    project_root = _project_root()
    root = Path(app.config["ROOT"])
    manager = JobManager(
        project_root=project_root,
        client_factory=lambda: CodexAppServerClient(study_loop_skill_root=SCRIPT_DIR.parent),
        topic_lock=lambda topic: session_lock(safe_path(root, topic)),
        preflight=_preflight_workflow,
        snapshot_workflow=_workflow_snapshot,
        postflight=_validate_workflow_completion,
    )
    app.config["JOB_MANAGER"] = manager
    return manager


def _slug_topic(value: str) -> str:
    value = re.sub(r"[\s/]+", "-", value.strip())
    value = re.sub(r"[^\w-]", "", value, flags=re.UNICODE)
    return value.lower()[:120]


_SESSION_START_KEYS = {
    "topic", "why", "successCriteria", "constraints", "outOfScope",
    "retentionInterval", "targetLevel", "timeBudget",
}
_ACTION_DATA_KEYS: dict[str, set[str]] = {
    "session_start": _SESSION_START_KEYS,
    "diagnostic_grade": {"confirmationToken", "selfExplanation"},
    "diagnostic_accept": {"adjustment"},
    "curriculum_revise": {"feedback"},
    "curriculum_accept": set(),
    "lesson_grade": {"confirmationToken", "selfExplanation", "resolution", "followupJobId"},
    "spaced_review": set(),
    "session_end": set(),
}


_GRADE_ACTIONS = {"diagnostic_grade", "lesson_grade"}


class InvalidTransition(ValueError):
    """A fixed action was requested before its Markdown prerequisites exist."""


def _lesson_url(topic: str, kind: str, name: str) -> str:
    return f"/{quote(topic, safe='')}/{kind}/{quote(name, safe='')}"


def _topic_is_diagnostic_complete(topic_dir: Path) -> bool:
    diagnostic = list_files(topic_dir, "diagnostic")
    return len(diagnostic) == 4 and all(item["graded"] for item in diagnostic) and (topic_dir / "diagnostic" / "summary.md").exists()


def _result_file_url(topic: str, result: Any) -> str | None:
    """Map only a validated Study Loop result path to a learner-facing page."""
    if not isinstance(result, dict) or not isinstance(result.get("resultPath"), str):
        return None
    parts = Path(result["resultPath"]).parts
    if len(parts) != 4 or parts[:2] != (".study", topic):
        return None
    _, _, kind, name = parts
    if kind not in {"diagnostic", "lessons"} or not name.endswith(".md") or name == "summary.md" or Path(name).name != name:
        return None
    root = Path(app.config["ROOT"])
    try:
        topic_dir = safe_path(root, topic)
        kind_dir = safe_path(root, topic, kind)
        candidate = safe_path(root, topic, kind, name)
    except Exception:
        return None
    if not topic_dir.is_dir() or topic_dir.is_symlink() or not _regular_file(candidate, kind_dir):
        return None
    return _lesson_url(topic, kind, name)


def _result_url(topic: str, action: str, result: Any) -> str:
    """Choose a local, server-derived continuation page for a completed job."""
    root = Path(app.config["ROOT"])
    try:
        topic_dir = safe_path(root, topic)
    except Exception:
        return "/"
    if action in {"diagnostic_accept", "curriculum_revise"}:
        return f"/{quote(topic, safe='')}/curriculum"
    if action == "diagnostic_grade":
        if _topic_is_diagnostic_complete(topic_dir):
            return f"/{quote(topic, safe='')}/curriculum"
        generated = _result_file_url(topic, result)
        if generated:
            return generated
        pending = next((item for item in list_files(topic_dir, "diagnostic") if not item["graded"]), None)
        return _lesson_url(topic, "diagnostic", pending["name"]) if pending else f"/{quote(topic, safe='')}/"
    if action == "session_start":
        generated = _result_file_url(topic, result)
        if generated:
            return generated
        pending = next((item for item in list_files(topic_dir, "diagnostic") if not item["graded"]), None)
        return _lesson_url(topic, "diagnostic", pending["name"]) if pending else f"/{quote(topic, safe='')}/"
    if action in {"curriculum_accept", "spaced_review", "lesson_grade"}:
        generated = _result_file_url(topic, result)
        if generated:
            return generated
        pending = next((item for item in list_files(topic_dir, "lessons") if not item["graded"]), None)
        return _lesson_url(topic, "lessons", pending["name"]) if pending else f"/{quote(topic, safe='')}/"
    return f"/{quote(topic, safe='')}/"


def _public_job(value: dict[str, Any]) -> dict[str, Any]:
    """Attach only server-computed navigation and acceptance state to a job."""
    public = dict(value)
    topic = public.get("topic")
    action = public.get("action")
    result = public.get("result")
    if public.get("status") == "completed" and isinstance(topic, str) and isinstance(action, str):
        public["nextUrl"] = _result_url(topic, action, result)
        try:
            public["canAcceptDiagnostic"] = action == "diagnostic_grade" and _topic_is_diagnostic_complete(safe_path(Path(app.config["ROOT"]), topic))
        except Exception:
            public["canAcceptDiagnostic"] = False
    else:
        public["nextUrl"] = None
        public["canAcceptDiagnostic"] = False
    if (
        public.get("status") == "completed"
        and action == "lesson_grade"
        and isinstance(result, dict)
        and result.get("nextAction") == "retry_or_continue"
        and isinstance(public.get("id"), str)
    ):
        public["lessonResolution"] = {"sourceJobId": public["id"], "choices": ["retry", "continue"]}
    else:
        public["lessonResolution"] = None
    return public


def _regular_file(path: Path, parent: Path) -> bool:
    """True only for a real regular file contained by its expected directory."""
    try:
        resolved = path.resolve(strict=True)
        parent_resolved = parent.resolve(strict=True)
    except OSError:
        return False
    return path.is_file() and not path.is_symlink() and (resolved == parent_resolved or parent_resolved in resolved.parents)


def _existing_session(topic: str) -> Path:
    topic_dir = safe_path(Path(app.config["ROOT"]), topic)
    if not topic_dir.is_dir() or topic_dir.is_symlink() or not _regular_file(topic_dir / "README.md", topic_dir):
        raise InvalidTransition("この操作には有効な学習セッションが必要です。")
    return topic_dir


def _diagnostic_complete(topic_dir: Path) -> bool:
    diagnostic_dir = topic_dir / "diagnostic"
    if not diagnostic_dir.is_dir() or diagnostic_dir.is_symlink() or not _regular_file(diagnostic_dir / "summary.md", diagnostic_dir):
        return False
    diagnostics = list_files(topic_dir, "diagnostic")
    if len(diagnostics) != 4:
        return False
    for item in diagnostics:
        path = diagnostic_dir / item["name"]
        if not _regular_file(path, diagnostic_dir):
            return False
        try:
            if not is_graded(path.read_text(encoding="utf-8")):
                return False
        except OSError:
            return False
    return True


def _curriculum_ready(topic_dir: Path) -> bool:
    return _diagnostic_complete(topic_dir) and _regular_file(topic_dir / "curriculum.md", topic_dir) and _regular_file(topic_dir / "RESOURCES.md", topic_dir)


def _require_transition(action: str, topic: str, payload: dict[str, Any] | None = None) -> None:
    """Enforce the workflow from Markdown, never from a browser or model claim."""
    topic_dir = _existing_session(topic)
    if action == "diagnostic_accept":
        if not _diagnostic_complete(topic_dir):
            raise InvalidTransition("診断の受理には、採点済みの診断4問と summary.md が必要です。")
        return
    if action in {"curriculum_revise", "curriculum_accept"}:
        if not _curriculum_ready(topic_dir):
            raise InvalidTransition("カリキュラム操作には、完了した診断と生成済みの curriculum.md・RESOURCES.md が必要です。")
        return
    if action == "diagnostic_grade":
        target = (payload or {}).get("target")
        if not isinstance(target, dict) or target.get("kind") != "diagnostic" or not isinstance(target.get("name"), str):
            raise InvalidTransition("診断の採点対象が確認できません。")
        diagnostics = list_files(topic_dir, "diagnostic")
        pending = next((item for item in diagnostics if not item["graded"]), None)
        path = topic_dir / "diagnostic" / target["name"]
        if pending is None or pending["name"] != target["name"] or not _regular_file(path, topic_dir / "diagnostic"):
            raise InvalidTransition("診断は未採点の次の問題から順に採点してください。")
        return
    if action == "lesson_grade":
        target = (payload or {}).get("target")
        if not isinstance(target, dict) or target.get("kind") != "lessons" or not isinstance(target.get("name"), str):
            raise InvalidTransition("lesson の採点対象が確認できません。")
        path = topic_dir / "lessons" / target["name"]
        if not _regular_file(path, topic_dir / "lessons"):
            raise InvalidTransition("採点対象の lesson が見つかりません。")
        try:
            if is_graded(path.read_text(encoding="utf-8")):
                raise InvalidTransition("採点済みの lesson はもう一度採点できません。")
        except OSError as exc:
            raise InvalidTransition("採点対象の lesson を読み込めません。") from exc
        return
    if action == "spaced_review":
        if not _curriculum_ready(topic_dir) or not any(item["graded"] for item in list_files(topic_dir, "lessons")):
            raise InvalidTransition("復習には、カリキュラムと採点済み lesson が必要です。")
        return
    if action == "session_end":
        return
    raise InvalidTransition("この操作の学習状態を確認できません。")


def _has_substantive_markdown_text(value: str) -> bool:
    """Ignore Markdown structure that does not communicate any session result."""
    placeholders = {"", "-", "—", "未設定", "未記入", "未入力", "なし", "n/a", "none", "tbd", "todo"}
    if value.strip().casefold() in placeholders:
        return False
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.fullmatch(r"(?:[-*_]\s*){3,}", line):
            continue
        if re.fullmatch(r"(?:[-+*]|\d+[.)])(?:\s+\[[ xX]\])?", line):
            continue
        return True
    return False


def _valid_session_end(text: str) -> bool:
    """Return whether README records a substantive completed-session summary."""
    ended = re.search(r"(?mi)^\*\*Ended\*\*:\s*(.*?)\s*$", text)
    summary = re.search(r"(?ims)^##\s+Summary\s*$\n?(.*?)(?=^#{1,2}\s|\Z)", text)
    values = (ended.group(1) if ended else "", summary.group(1) if summary else "")
    return all(_has_substantive_markdown_text(value) for value in values)


def _preflight_workflow(action: str, topic: str, payload: dict[str, Any]) -> None:
    """Repeat the server-owned transition check after the topic lock is held."""
    if action == "session_start":
        if safe_path(Path(app.config["ROOT"]), topic).exists():
            raise InvalidTransition("同名の学習セッションがすでにあります。")
        return
    if action == "lesson_grade" and payload.get("resolution") in {"retry", "continue"}:
        _existing_session(topic)
        return
    if action == "session_end":
        readme = _existing_session(topic) / "README.md"
        try:
            if _valid_session_end(readme.read_text(encoding="utf-8")):
                raise InvalidTransition("この学習セッションはすでに終了しています。")
        except OSError as exc:
            raise InvalidTransition("学習セッションの README を読み込めません。") from exc
        return
    _require_transition(action, topic, payload)


def _workflow_snapshot(topic: str) -> dict[str, Any]:
    """Capture Markdown facts before a turn, while its topic lock is held."""
    topic_dir = safe_path(Path(app.config["ROOT"]), topic)
    if not topic_dir.is_dir() or topic_dir.is_symlink():
        return {"files": {}, "lessons": set()}
    files: dict[str, str] = {}
    for path in topic_dir.rglob("*.md"):
        if not _regular_file(path, topic_dir):
            continue
        try:
            files[str(path.relative_to(topic_dir))] = _file_revision(path)
        except OSError:
            continue
    return {"files": files, "lessons": {item["name"] for item in list_files(topic_dir, "lessons")}}


def _result_parts(result: dict[str, Any]) -> tuple[str, ...] | None:
    value = result.get("resultPath")
    if not isinstance(value, str):
        return None
    return Path(value).parts[2:]


def _require_result(result: dict[str, Any], *, next_action: str, parts: tuple[str, ...] | None = None) -> tuple[str, ...] | None:
    if result.get("nextAction") != next_action:
        raise ValueError("Codex の完了結果が学習フローと一致しません。")
    actual = _result_parts(result)
    if parts is not None and actual != parts:
        raise ValueError("Codex の完了成果物が学習フローと一致しません。")
    return actual


def _ungraded_name(topic_dir: Path, kind: str, name: str) -> bool:
    return any(item["name"] == name and not item["graded"] for item in list_files(topic_dir, kind))


def _target_is_graded(topic_dir: Path, payload: dict[str, Any], kind: str) -> str:
    target = payload.get("target")
    if not isinstance(target, dict) or target.get("kind") != kind or not isinstance(target.get("name"), str):
        raise ValueError("Codex の採点対象が不正です。")
    path = topic_dir / kind / target["name"]
    if not _regular_file(path, topic_dir / kind):
        raise ValueError("Codex の採点対象が見つかりません。")
    try:
        if not is_graded(path.read_text(encoding="utf-8")):
            raise ValueError("Codex は採点対象を採点していません。")
    except OSError as exc:
        raise ValueError("Codex の採点対象を読み込めません。") from exc
    return target["name"]


def _new_ungraded_lesson(topic_dir: Path, snapshot: dict[str, Any]) -> set[str]:
    before = snapshot.get("lessons", set()) if isinstance(snapshot, dict) else set()
    if not isinstance(before, set):
        before = set()
    return {item["name"] for item in list_files(topic_dir, "lessons") if not item["graded"] and item["name"] not in before}


def _validate_workflow_completion(
    action: str,
    topic: str,
    payload: dict[str, Any],
    result: dict[str, Any],
    snapshot: Any,
) -> None:
    """Verify Codex changed the durable Markdown state promised by one action."""
    topic_dir = safe_path(Path(app.config["ROOT"]), topic)
    state = snapshot if isinstance(snapshot, dict) else {"files": {}, "lessons": set()}
    if action == "session_start":
        _existing_session(topic)
        if not _regular_file(topic_dir / "curriculum.md", topic_dir):
            raise ValueError("Codex は学習セッションの骨組みを作成していません。")
        diagnostics = list_files(topic_dir, "diagnostic")
        actual = _require_result(result, next_action="answer")
        if actual is None or len(actual) != 2 or actual[0] != "diagnostic" or not diagnostics or not _ungraded_name(topic_dir, "diagnostic", actual[1]):
            raise ValueError("Codex は回答可能な診断を作成していません。")
        return
    if action == "diagnostic_grade":
        _target_is_graded(topic_dir, payload, "diagnostic")
        if _diagnostic_complete(topic_dir):
            _require_result(result, next_action="review_curriculum", parts=("diagnostic", "summary.md"))
            return
        actual = _require_result(result, next_action="answer")
        if actual is None or len(actual) != 2 or actual[0] != "diagnostic" or not _ungraded_name(topic_dir, "diagnostic", actual[1]):
            raise ValueError("Codex は次の未採点診断を生成していません。")
        return
    if action == "diagnostic_accept":
        if not _curriculum_ready(topic_dir):
            raise ValueError("Codex は curriculum.md と RESOURCES.md を作成していません。")
        previous = state.get("files", {})
        changed = any(
            isinstance(previous, dict) and previous.get(name) != _file_revision(topic_dir / name)
            for name in ("curriculum.md", "RESOURCES.md")
        )
        if not changed:
            raise ValueError("Codex は診断受理後の学習資産を更新していません。")
        actual = _require_result(result, next_action="review_curriculum")
        if actual not in {("curriculum.md",), ("RESOURCES.md",)}:
            raise ValueError("Codex の診断受理成果物が不正です。")
        return
    if action == "curriculum_revise":
        if not _curriculum_ready(topic_dir):
            raise ValueError("Codex はカリキュラム資産を維持していません。")
        previous = state.get("files", {})
        changed = any(
            isinstance(previous, dict) and previous.get(name) != _file_revision(topic_dir / name)
            for name in ("curriculum.md", "RESOURCES.md")
        )
        if not changed:
            raise ValueError("Codex はカリキュラムを更新していません。")
        actual = _require_result(result, next_action="review_curriculum")
        if actual not in {("curriculum.md",), ("RESOURCES.md",)}:
            raise ValueError("Codex のカリキュラム更新成果物が不正です。")
        return
    if action == "curriculum_accept":
        if not _curriculum_ready(topic_dir):
            raise ValueError("Codex は診断後のカリキュラムを確認できません。")
        actual = _require_result(result, next_action="answer")
        new_lessons = _new_ungraded_lesson(topic_dir, state)
        if actual is None or len(actual) != 2 or actual[0] != "lessons" or actual[1] not in new_lessons:
            raise ValueError("Codex は最初の回答可能な lesson を作成していません。")
        return
    if action == "lesson_grade":
        if payload.get("resolution") in {"retry", "continue"}:
            actual = _require_result(result, next_action="answer")
            new_lessons = _new_ungraded_lesson(topic_dir, state)
            if actual is None or len(actual) != 2 or actual[0] != "lessons" or actual[1] not in new_lessons:
                raise ValueError("Codex は retry/continue 用の新しい lesson を作成していません。")
            return
        target_name = _target_is_graded(topic_dir, payload, "lessons")
        next_action = result.get("nextAction")
        actual = _result_parts(result)
        if next_action == "answer" and actual is not None and len(actual) == 2 and actual[0] == "lessons" and actual[1] != target_name and _ungraded_name(topic_dir, "lessons", actual[1]):
            return
        if next_action in {"retry_or_continue", "done"} and actual in {None, ("lessons", target_name)}:
            return
        raise ValueError("Codex の lesson 採点後の遷移が不正です。")
    if action == "spaced_review":
        if not _curriculum_ready(topic_dir):
            raise ValueError("Codex は復習の前提となるカリキュラムを確認できません。")
        actual = _require_result(result, next_action="answer")
        new_lessons = _new_ungraded_lesson(topic_dir, state)
        if actual is None or len(actual) != 2 or actual[0] != "lessons" or actual[1] not in new_lessons:
            raise ValueError("Codex は別バリエーションの復習 lesson を作成していません。")
        return
    if action == "session_end":
        readme = _existing_session(topic) / "README.md"
        text = readme.read_text(encoding="utf-8")
        previous = state.get("files", {})
        if not isinstance(previous, dict) or previous.get("README.md") == _file_revision(readme):
            raise ValueError("Codex は README を更新していません。")
        if not _valid_session_end(text):
            raise ValueError("Codex は README に Ended と Summary を記録していません。")
        _require_result(result, next_action="done", parts=("README.md",))
        return
    raise ValueError("Codex の完了操作が不正です。")


def _file_revision(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _new_confirmation(topic: str, kind: str, name: str, file_path: Path, answer: str, tags: list[str], note: str) -> str:
    token = secrets.token_urlsafe(32)
    record = {
        "topic": topic, "kind": kind, "name": name, "path": str(file_path.resolve()),
        "revision": _file_revision(file_path), "answer": answer, "tags": tags, "note": note.strip(),
    }
    with _CONFIRMATIONS_LOCK:
        app.config["CONFIRMATIONS"][token] = record
    return token


def _confirmation_record(token: Any, *, consume: bool = False) -> tuple[str, dict[str, Any]]:
    if not isinstance(token, str) or len(token) < 20:
        raise ValueError("回答確認が見つかりません。回答を保存し直してください。")
    with _CONFIRMATIONS_LOCK:
        record = app.config["CONFIRMATIONS"].get(token)
        if not isinstance(record, dict):
            raise ValueError("この回答確認は期限切れか、すでに使われています。")
        path = Path(str(record.get("path", "")))
        root = Path(app.config["ROOT"])
        safe = safe_path(root, str(record.get("topic", "")), str(record.get("kind", "")), str(record.get("name", "")))
        if path != safe or not safe.exists() or _file_revision(safe) != record.get("revision"):
            app.config["CONFIRMATIONS"].pop(token, None)
            raise ValueError("回答が変更されました。最新の回答を保存して確認してください。")
        if consume:
            app.config["CONFIRMATIONS"].pop(token, None)
        return token, record


def _reserve_confirmation(token: Any) -> tuple[str, dict[str, Any]]:
    """Reserve one confirmation while its job is queued, without a replay race."""
    with _CONFIRMATIONS_LOCK:
        token_value, record = _confirmation_record(token)
        if record.get("_reserved") is True:
            raise ValueError("この回答確認はすでに採点を開始しています。")
        record["_reserved"] = True
        return token_value, record


def _release_confirmation_reservation(token: str) -> None:
    with _CONFIRMATIONS_LOCK:
        record = app.config["CONFIRMATIONS"].get(token)
        if isinstance(record, dict):
            record.pop("_reserved", None)


def _consume_confirmation_reservation(token: str) -> None:
    with _CONFIRMATIONS_LOCK:
        record = app.config["CONFIRMATIONS"].get(token)
        if not isinstance(record, dict) or record.get("_reserved") is not True:
            raise ValueError("この回答確認は期限切れか、すでに使われています。")
        app.config["CONFIRMATIONS"].pop(token, None)


def _validated_job_request(body: Any) -> tuple[str, str, dict[str, Any]]:
    if not isinstance(body, dict) or set(body) != {"action", "data"}:
        raise ValueError("操作データが不正です。")
    action = body.get("action")
    data = body.get("data")
    if not isinstance(action, str) or action not in ALLOWED_ACTIONS or not isinstance(data, dict):
        raise ValueError("許可されていない操作です。")
    allowed = _ACTION_DATA_KEYS[action]
    if set(data) - allowed:
        raise ValueError("この操作には指定できない値が含まれています。")
    if action == "session_start":
        if set(data) != _SESSION_START_KEYS or not isinstance(data.get("topic"), str):
            raise ValueError("新しいセッションの情報が不足しています。")
        topic = _slug_topic(data["topic"])
        criteria = data.get("successCriteria")
        if not topic or not isinstance(criteria, list) or not 2 <= len(criteria) <= 4:
            raise ValueError("トピックまたは達成条件が不正です。")
        if not isinstance(data.get("targetLevel"), int) or not 1 <= data["targetLevel"] <= 5:
            raise ValueError("目標レベルは 1〜5 で指定してください。")
        for key in _SESSION_START_KEYS - {"successCriteria", "targetLevel"}:
            if not isinstance(data.get(key), str) or len(data[key].strip()) > 2000:
                raise ValueError("新しいセッションの情報が不正です。")
        if any(not isinstance(item, str) or not item.strip() or len(item) > 400 for item in criteria):
            raise ValueError("達成条件が不正です。")
        if safe_path(Path(app.config["ROOT"]), topic).exists():
            raise InvalidTransition("同名の学習セッションがすでにあります。")
        return action, topic, data
    if action == "lesson_grade" and "followupJobId" in data:
        if set(data) != {"followupJobId", "resolution"} or data.get("resolution") not in {"retry", "continue"} or not isinstance(data.get("followupJobId"), str):
            raise ValueError("次の操作が不正です。")
        try:
            source = _job_manager().reserve_lesson_resolution(data["followupJobId"])
        except KeyError as exc:
            raise ValueError("採点結果が見つかりません。") from exc
        source_result = getattr(source, "result", None)
        source_payload = getattr(source, "payload", None)
        if (
            getattr(source, "status", None) != "completed"
            or getattr(source, "action", None) != "lesson_grade"
            or not isinstance(getattr(source, "topic", None), str)
            or not isinstance(source_result, dict)
            or source_result.get("nextAction") != "retry_or_continue"
            or not isinstance(source_payload, dict)
            or not isinstance(source_payload.get("target"), dict)
            or not isinstance(source_payload.get("feedback"), dict)
        ):
            raise ValueError("この採点結果から次の操作は開始できません。")
        internal = {
            "target": source_payload["target"], "feedback": source_payload["feedback"], "resolution": data["resolution"],
            "_lessonResolutionSource": data["followupJobId"],
        }
        return action, source.topic, internal
    if action in _GRADE_ACTIONS:
        allowed_grade = _ACTION_DATA_KEYS[action]
        if "confirmationToken" not in data or set(data) - allowed_grade:
            raise ValueError("回答確認が不正です。")
        _, record = _confirmation_record(data["confirmationToken"])
        expected_kind = "diagnostic" if action == "diagnostic_grade" else "lessons"
        if record.get("kind") != expected_kind:
            raise ValueError("この回答には指定された採点操作を使えません。")
        if "selfExplanation" in data and (not isinstance(data["selfExplanation"], str) or len(data["selfExplanation"]) > 4000):
            raise ValueError("自己説明が不正です。")
        if "resolution" in data and data["resolution"] not in {"retry", "continue"}:
            raise ValueError("次の操作が不正です。")
        internal = {key: value for key, value in data.items() if key != "confirmationToken"}
        internal["target"] = {"kind": record["kind"], "name": record["name"]}
        internal["feedback"] = {"tags": record["tags"], "note": record["note"]}
        internal["_confirmedAnswer"] = {
            "kind": record["kind"], "name": record["name"], "revision": record["revision"],
        }
        _require_transition(action, str(record["topic"]), internal)
        return action, str(record["topic"]), internal
    topic = request.args.get("topic", "")
    if not re.fullmatch(r"[\w-]{1,120}", topic, flags=re.UNICODE):
        raise ValueError("対象セッションが不正です。")
    for value in data.values():
        if not isinstance(value, str) or len(value) > 4000:
            raise ValueError("操作データが不正です。")
    _require_transition(action, topic, data)
    return action, topic, data


@app.route("/api/codex/status")
def codex_status() -> Any:
    installed = bool(_codex_path())
    backend = _backend()
    last = getattr(app.config.get("JOB_MANAGER"), "last_connection_status", None)
    if backend == "manual":
        message = "手動モードです。Markdown を保存し、Claude Code で続けられます。"
    elif not installed:
        message = "Codex が見つかりません。手動で保存して Claude Code を利用できます。"
    elif isinstance(last, AppServerStatus):
        message = last.message
    else:
        message = "Codex は開始操作を選んだときだけ起動します。"
    return jsonify({"backend": backend, "installed": installed, "message": message, "recovery": last.recovery if isinstance(last, AppServerStatus) else None})


@app.route("/api/jobs", methods=["POST"])
def create_codex_job() -> Any:
    require_csrf()
    if _backend() == "manual":
        return jsonify({"error": "manual_mode", "message": "手動モードでは Codex を開始しません。"}), 409
    if not _codex_path():
        return jsonify({"error": "codex_missing", "message": "Codex が見つかりません。手動で続けてください。"}), 503
    body = request.get_json(silent=True)
    try:
        with _CONFIRMATIONS_LOCK:
            action, topic, data = _validated_job_request(body)
            lesson_resolution_source = data.pop("_lessonResolutionSource", None)
            raw_data = body.get("data") if isinstance(body, dict) else None
            token = raw_data.get("confirmationToken") if isinstance(raw_data, dict) else None
            reserved_token: str | None = None
            if action in _GRADE_ACTIONS and isinstance(token, str):
                reserved_token, _ = _reserve_confirmation(token)
            try:
                job = _job_manager().create_job(action, topic, data)
                if isinstance(lesson_resolution_source, str):
                    _job_manager().commit_lesson_resolution(lesson_resolution_source)
            except Exception:
                if reserved_token is not None:
                    _release_confirmation_reservation(reserved_token)
                if isinstance(lesson_resolution_source, str):
                    _job_manager().release_lesson_resolution(lesson_resolution_source)
                raise
            if reserved_token is not None:
                _consume_confirmation_reservation(reserved_token)
    except InvalidTransition as exc:
        return jsonify({"error": "invalid_transition", "message": str(exc)}), 409
    except ValueError as exc:
        return jsonify({"error": "invalid_request", "message": str(exc)}), 400
    public = _public_job(job.public())
    response = jsonify(public)
    response.status_code = 202
    response.headers["Location"] = url_for("codex_job_page", job_id=public["id"])
    return response


@app.route("/api/jobs/<job_id>/events")
def codex_job_events(job_id: str) -> Response:
    try:
        after = int(request.headers.get("Last-Event-ID") or request.args.get("after", "0"))
    except ValueError:
        after = 0

    @stream_with_context
    def stream() -> Any:
        try:
            events = _job_manager().events_after(job_id, after)
        except KeyError:
            yield "event: error\ndata: {\"message\":\"Job not found\"}\n\n"
            return
        for event in events:
            data = json.dumps(_public_job(event.data), ensure_ascii=False, separators=(",", ":"))
            yield f"id: {event.id}\nevent: {event.kind}\ndata: {data}\n\n"
        # EventSource reconnects after this heartbeat. No job state is kept in
        # the browser and reconnect therefore remains safe after a reload.
        yield ": keepalive\n\n"

    return Response(stream(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.route("/api/jobs/<job_id>/responses", methods=["POST"])
def respond_to_codex_job(job_id: str) -> Any:
    require_csrf()
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) - {"answers", "decision"}:
        return jsonify({"error": "invalid_request", "message": "応答が不正です。"}), 400
    try:
        return jsonify(_public_job(_job_manager().respond(job_id, body).public()))
    except KeyError:
        abort(404)
    except ValueError as exc:
        return jsonify({"error": "invalid_request", "message": str(exc)}), 400


@app.route("/api/jobs/<job_id>/cancel", methods=["POST"])
def cancel_codex_job(job_id: str) -> Any:
    require_csrf()
    try:
        return jsonify(_public_job(_job_manager().cancel(job_id).public()))
    except KeyError:
        abort(404)


def list_sessions() -> list[dict[str, Any]]:
    root: Path = app.config["ROOT"]
    if not root.exists():
        return []
    try:
        root_resolved = root.resolve(strict=True)
    except OSError:
        return []
    sessions: list[dict[str, Any]] = []
    for d in sorted(root.iterdir()):
        readme = d / "README.md"
        if d.is_symlink() or not d.is_dir() or not _regular_file(readme, d):
            continue
        try:
            resolved_dir = d.resolve(strict=True)
        except OSError:
            continue
        if root_resolved not in resolved_dir.parents:
            continue
        try:
            text = readme.read_text(encoding="utf-8")
        except OSError:
            continue
        h = parse_header(text)
        sessions.append(
            {
                "slug": d.name,
                "topic": h.get("topic") or d.name,
                "current_level": h.get("Current Level", "-"),
                "target_level": h.get("Target Level", "-"),
                "stage": h.get("Stage", "-"),
                "started": h.get("Started", "-"),
                "last_updated": h.get("Last updated", "-"),
                "ended": h.get("Ended", "-"),
            }
        )
    return sessions


def learning_overview(session: dict[str, Any]) -> dict[str, Any]:
    """Home / 学習一覧 / レッスンナビで使う、1セッション分の表示データ。"""
    topic = session["slug"]
    topic_dir = safe_path(app.config["ROOT"], topic)
    readme = topic_dir / "README.md"
    text = readme.read_text(encoding="utf-8")
    progress = parse_progress(text)
    diagnostic = list_files(topic_dir, "diagnostic")
    lessons = list_files(topic_dir, "lessons")

    active_lesson = next((item for item in lessons if not item["graded"]), None)
    if active_lesson is None and lessons:
        active_lesson = lessons[-1]
    active_diagnostic = next((item for item in diagnostic if not item["graded"]), None)
    if active_diagnostic is None and diagnostic:
        active_diagnostic = diagnostic[-1]

    if active_lesson:
        resume_url = url_for("lesson_view", topic=topic, name=active_lesson["name"])
        resume_title = active_lesson["title"]
        resume_kind = "lesson"
        resume_name = active_lesson["name"]
    elif active_diagnostic:
        resume_url = url_for("diagnostic_view", topic=topic, name=active_diagnostic["name"])
        resume_title = active_diagnostic["title"]
        resume_kind = "diagnostic"
        resume_name = active_diagnostic["name"]
    elif (topic_dir / "curriculum.md").exists():
        resume_url = url_for("curriculum", topic=topic)
        resume_title = "カリキュラムを確認する"
        resume_kind = "curriculum"
        resume_name = ""
    else:
        resume_url = url_for("learning", topic=topic, _anchor=f"course-{topic}")
        resume_title = "学習内容を確認する"
        resume_kind = "overview"
        resume_name = ""

    graded_items = [item for item in lessons if item["graded"]]
    latest_score = None
    latest_scored_title = None
    for item in reversed(graded_items):
        lesson_path = safe_path(topic_dir, "lessons", item["name"])
        try:
            score = extract_score(lesson_path.read_text(encoding="utf-8"))
        except OSError:
            score = None
        if score:
            latest_score = score
            latest_scored_title = item["title"]
            break

    active_stage = next((stage for stage in progress if stage["done"] < stage["total"]), None)
    if active_stage is None and progress:
        active_stage = progress[-1]
    if active_stage:
        done = active_stage["done"]
        total = active_stage["total"]
    else:
        done = sum(stage["done"] for stage in progress)
        total = sum(stage["total"] for stage in progress)
    pct = round(done / total * 100) if total else 0

    success_md = _section_body(_section_body(text, "## Mission"), "### Success looks like").strip()
    if not success_md:
        success_md = _section_body(text, "## Goal").strip()
    success = re.sub(r"(?m)^\s*[-*]\s+", "", success_md).splitlines()
    success_caption = next((line.strip() for line in success if line.strip()), "")

    return {
        **session,
        "diagnostic": diagnostic,
        "lessons": lessons,
        "progress": progress,
        "active_stage": active_stage,
        "done": done,
        "total": total,
        "pct": pct,
        "resume_url": resume_url,
        "resume_title": resume_title,
        "resume_kind": resume_kind,
        "resume_name": resume_name,
        "latest_score": latest_score,
        "latest_scored_title": latest_scored_title,
        "success_caption": success_caption,
        "readme_html": render_markdown(text),
        "library_url": url_for("learning", topic=topic, _anchor=f"course-{topic}"),
        "has_glossary": (topic_dir / "GLOSSARY.md").exists(),
        "has_resources": (topic_dir / "RESOURCES.md").exists(),
    }


def learning_overviews() -> list[dict[str, Any]]:
    """更新日の新しい順で表示する。日付が無い既存データは末尾に置く。"""
    sessions = [learning_overview(session) for session in list_sessions()]
    return sorted(
        sessions,
        key=lambda item: (
            item["last_updated"] not in {"", "-"},
            item["last_updated"] if item["last_updated"] != "-" else "",
        ),
        reverse=True,
    )


def list_files(topic_dir: Path, subdir: str) -> list[dict[str, Any]]:
    """diagnostic/ または lessons/ のファイル一覧。"""
    sub = topic_dir / subdir
    if sub.is_symlink() or not sub.is_dir():
        return []
    try:
        topic_resolved = topic_dir.resolve(strict=True)
        sub_resolved = sub.resolve(strict=True)
    except OSError:
        return []
    if topic_resolved not in sub_resolved.parents:
        return []
    files: list[dict[str, Any]] = []
    for f in sorted(sub.glob("*.md")):
        if f.name == "summary.md":
            continue
        if not _regular_file(f, sub):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        # Title: 先頭の `# ...` 行
        title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else f.stem
        # A heading alone is not evidence of grading; use the same semantic
        # predicate as every workflow gate.
        graded = is_graded(text)
        files.append(
            {
                "name": f.name,
                "stem": f.stem,
                "title": title,
                "graded": graded,
            }
        )
    return files


# ---------- Markdown section parsing ----------


def parse_header(text: str) -> dict[str, str]:
    """`# Title` 直後にある `**Key**: value` 行を辞書化。topic は `# Study Loop: <topic>` から抽出。"""
    headers: dict[str, str] = {}
    title_match = re.search(r"^#\s+Study Loop:\s+(.+)$", text, re.MULTILINE)
    if title_match:
        headers["topic"] = title_match.group(1).strip()
    else:
        title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        if title_match:
            headers["topic"] = title_match.group(1).strip()
    for line in text.splitlines():
        m = re.match(r"\*\*([^*]+)\*\*:\s*(.*)", line)
        if m:
            headers[m.group(1).strip()] = m.group(2).strip()
        if line.startswith("## ") and headers:
            break
    return headers


def parse_progress(readme_text: str) -> list[dict[str, Any]]:
    """`## Progress` セクションの `- Stage X (Name): a / b` をパース。"""
    section = _section_body(readme_text, "## Progress")
    if not section:
        return []
    stages: list[dict[str, Any]] = []
    for m in re.finditer(
        r"-\s*Stage\s*(\d+)\s*\(([^)]+)\):\s*(\d+)\s*/\s*(\d+)", section
    ):
        idx, name, done, total = m.groups()
        done_i, total_i = int(done), int(total)
        stages.append(
            {
                "index": int(idx),
                "name": name.strip(),
                "done": done_i,
                "total": total_i,
                "pct": (done_i / total_i * 100) if total_i else 0,
            }
        )
    return stages


def parse_profile(readme_text: str) -> dict[str, list[str]]:
    """`## Profile` 内の `### Strong` / `### Weak` を抽出。"""
    section = _section_body(readme_text, "## Profile")
    out: dict[str, list[str]] = {"strong": [], "weak": []}
    if not section:
        return out
    for label, key in [("### Strong", "strong"), ("### Weak", "weak")]:
        body = _section_body(section, label)
        if not body:
            continue
        tags: list[str] = []
        for line in body.splitlines():
            mline = re.match(r"-\s+(.+)", line.strip())
            if mline:
                v = mline.group(1).strip()
                if v and v != "(まだなし)":
                    tags.append(v)
        out[key] = tags
    return out


def _section_body(text: str, header: str) -> str:
    """与えられた header（例: '## Progress'）の本文を返す。次の同階層 header または末尾まで。"""
    level = len(header) - len(header.lstrip("#"))
    head_re = re.escape(header)
    next_re = r"\n#{1," + str(level) + r"}\s"
    pattern = rf"(?ms){head_re}\s*\n(.*?)(?={next_re}|\Z)"
    m = re.search(pattern, text)
    return m.group(1) if m else ""


# ---------- Answer field extraction / replacement ----------


ANSWER_HEADER = "## 回答欄"
GRADING_HEADER = "## 採点"


def extract_answer(md_text: str) -> str:
    """`## 回答欄` セクションから HTML コメントを除いた本文を取り出す。"""
    body = _section_body(md_text, ANSWER_HEADER)
    if not body:
        return ""
    # Template and submission comments are not answers. Structured slot
    # comments are deliberately retained so multipart code answers can be
    # restored to the same fields without parsing their code as Markdown.
    cleaned = re.sub(r"<!--(?!\s*/?study-answer\b).*?-->", "", body, flags=re.DOTALL)
    # `---` 区切りより前まで（ヒント以降を含めない）
    cleaned = re.split(r"^---\s*$", cleaned, maxsplit=1, flags=re.MULTILINE)[0]
    return cleaned.strip()


def replace_answer(md_text: str, new_answer: str) -> str:
    """`## 回答欄` 直後の本文を new_answer で置換。`---` や次の `## ` の手前までを差し替え。"""
    submitted_at = datetime.now().astimezone().isoformat(timespec="seconds")
    pattern = re.compile(
        rf"(?ms)({re.escape(ANSWER_HEADER)}\s*\n).*?(?=^---\s*$|^##\s)",
    )
    submitted_body = f"\n<!-- 提出済み: {submitted_at} -->\n\n{new_answer}\n\n"
    # A callable replacement is required: a learner may legitimately submit
    # regex backreferences (``\1`` / ``\g<name>``) or Windows paths, and a
    # replacement string would interpret those backslashes as regex escapes.
    new_text, n = pattern.subn(lambda match: match.group(1) + submitted_body, md_text, count=1)
    if n == 0:
        # フォールバック: ANSWER_HEADER が見つからない or 末尾まで読み込まれた場合
        return md_text
    return new_text


def is_graded(md_text: str) -> bool:
    section = _section_body(md_text, GRADING_HEADER)
    return bool(section.strip()) and "_未採点_" not in section


def extract_score(md_text: str) -> str | None:
    section = _section_body(md_text, GRADING_HEADER)
    m = re.search(r"\*\*Score\*\*:\s*([\d.]+)", section)
    return m.group(1) if m else None


def score_feedback(score: str | None) -> dict[str, str]:
    """0.0–1.0 の総合スコアを、UIで即読できる3段階へ変換する。"""
    try:
        value = float(score) if score is not None else None
    except ValueError:
        value = None
    if value is None:
        return {"state": "pending", "mark": "—", "label": "未採点"}
    if value >= 0.8:
        return {"state": "correct", "mark": "○", "label": "正解"}
    if value >= 0.5:
        return {"state": "partial", "mark": "△", "label": "一部修正が必要"}
    return {"state": "incorrect", "mark": "×", "label": "不正解"}


# ---------- Routes ----------


@app.context_processor
def inject_globals() -> dict[str, Any]:
    return {
        "render_md": render_markdown,
        "csrf_token": csrf_token,
        "backend": _backend(),
    }


# 404/403/500 をブランド付きの error.html で返す（デッドエンドにしない）
_ERROR_COPY = {
    403: ("アクセスできません", "このパスは表示できません。"),
    404: ("ページが見つかりません", "URL が変わったか、まだ生成されていない課題かもしれません。"),
    500: ("サーバーエラー", "予期しないエラーが発生しました。サーバーのログを確認してください。"),
}


@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(500)
def handle_error(err: Any) -> Any:
    code = getattr(err, "code", 500) or 500
    message, detail = _ERROR_COPY.get(code, _ERROR_COPY[500])
    name = getattr(err, "name", "Error")
    return render_template(
        "error.html", code=code, name=name, message=message, detail=detail
    ), code


# ---------- New-session setup and local job pages ----------


def _setup_from_form() -> dict[str, Any]:
    values = {
        "topic": request.form.get("topic", "").strip(),
        "why": request.form.get("why", "").strip(),
        "constraints": request.form.get("constraints", "").strip(),
        "outOfScope": request.form.get("out_of_scope", "").strip(),
        "retentionInterval": request.form.get("retention_interval", "").strip(),
        "timeBudget": request.form.get("time_budget", "").strip(),
    }
    criteria = [line.strip().lstrip("- ").strip() for line in request.form.get("success_criteria", "").splitlines()]
    values["successCriteria"] = [line for line in criteria if line]
    try:
        values["targetLevel"] = int(request.form.get("target_level", ""))
    except ValueError:
        values["targetLevel"] = 0
    if not _slug_topic(values["topic"]) or not 2 <= len(values["successCriteria"]) <= 4 or not 1 <= values["targetLevel"] <= 5:
        abort(400, "トピック、達成条件 2〜4 個、目標レベルを確認してください。")
    text_keys = {"topic", "why", "constraints", "outOfScope", "retentionInterval", "timeBudget"}
    if any(not values[key] or len(values[key]) > 1000 for key in text_keys):
        abort(400, "セットアップの入力を確認してください。")
    if any(len(item) > 400 for item in values["successCriteria"]):
        abort(400, "達成条件を短くしてください。")
    return values


def _manual_session_files(data: dict[str, Any]) -> str:
    slug = _slug_topic(data["topic"])
    root = Path(app.config["ROOT"])
    topic_dir = safe_path(root, slug)
    with session_lock(topic_dir):
        if topic_dir.exists():
            raise ValueError("同名の学習セッションがすでにあります。")
        topic_dir.mkdir(parents=True)
        criteria = "\n".join(f"- {item}" for item in data["successCriteria"])
        readme = f"""# Study Loop: {data['topic']}

**Started**: {datetime.now().astimezone().date().isoformat()}
**Last updated**: {datetime.now().astimezone().date().isoformat()}
**Format**: interactive
**Target Level**: {data['targetLevel']}
**Current Level**: -
**Confidence**: -
**Retention Interval**: {data['retentionInterval']}
**Time Budget**: {data['timeBudget']}
**Stage**: -
**Diagnostic complete**: false
**Ended**: -

## Mission

### Why

{data['why']}

### Success looks like

{criteria}

### Constraints

- {data['constraints']}

### Out of scope

- {data['outOfScope']}

## Profile

### Strong
- (まだなし)

### Weak
- (まだなし)

## Progress

- Stage 1 (Foundation): 0 / 0
- Stage 2 (Practical): 0 / 0
- Stage 3 (Design): 0 / 0

## Recent scores

(空、最新5問のスコアをここに溜める)
"""
        curriculum = f"""# Curriculum: {data['topic']}

診断結果を受けて、Claude Code または Codex でこのカリキュラムを作成します。
"""
        atomic_write(topic_dir / "README.md", readme)
        atomic_write(topic_dir / "curriculum.md", curriculum)
        atomic_write(topic_dir / "RESOURCES.md", "# Resources\n\n診断後に信頼できる資料を選びます。\n")
        atomic_write(topic_dir / "GLOSSARY.md", "# Glossary\n\n## Terms\n\n")
        atomic_write(topic_dir / "INSIGHTS.md", "# Insights\n\n")
        _ensure_feedback_md(topic_dir)
    return slug


@app.route("/setup", methods=["POST"])
def setup_session() -> Any:
    require_csrf()
    session["study_loop_setup"] = _setup_from_form()
    return redirect(url_for("setup_confirmation"))


@app.route("/setup/confirm")
def setup_confirmation() -> Any:
    draft = session.get("study_loop_setup")
    if not isinstance(draft, dict):
        return redirect(url_for("index"))
    return render_template("setup_confirmation.html", draft=draft)


@app.route("/setup/manual", methods=["POST"])
def save_manual_setup() -> Any:
    require_csrf()
    draft = session.get("study_loop_setup")
    if not isinstance(draft, dict):
        abort(400)
    try:
        slug = _manual_session_files(draft)
    except ValueError as exc:
        abort(409, str(exc))
    return redirect(url_for("learning", topic=slug, _anchor=f"course-{slug}"))


@app.route("/jobs/<job_id>")
def codex_job_page(job_id: str) -> Any:
    try:
        job = _public_job(_job_manager().get_job(job_id).public())
    except KeyError:
        abort(404)
    return render_template("job.html", job=job)


@app.route("/")
def index() -> str:
    sessions = learning_overviews()
    active_sessions = [item for item in sessions if item["ended"] in {"", "-"}]
    resume = active_sessions[0] if active_sessions else (sessions[0] if sessions else None)
    return render_template("index.html", sessions=sessions, resume=resume)


@app.route("/learning")
def learning() -> str:
    return render_template(
        "learning.html",
        sessions=learning_overviews(),
        selected_topic=request.args.get("topic", ""),
    )


@app.route("/new")
def new_learning() -> str:
    return render_template("new_learning.html")


@app.route("/<topic>/")
def dashboard(topic: str) -> Any:
    topic_dir = safe_path(app.config["ROOT"], topic)
    readme = topic_dir / "README.md"
    if not readme.exists():
        abort(404)
    return redirect(url_for("learning", topic=topic, _anchor=f"course-{topic}"))


def _support_return_url(topic: str) -> str:
    """補助資料から戻るローカルのレッスンURLを安全に解決する。"""
    candidate = request.args.get("return_to", "").strip()
    parsed = urlparse(candidate)
    segments = parsed.path.split("/")
    if (
        candidate
        and not parsed.scheme
        and not parsed.netloc
        and not parsed.fragment
        and len(segments) == 4
        and segments[0] == ""
        and segments[1] == topic
        and segments[2] in {"diagnostic", "lessons"}
        and segments[3]
    ):
        target = safe_path(app.config["ROOT"], topic, segments[2], segments[3])
        if target.is_file() and target.suffix == ".md":
            return parsed.path
    return url_for("learning", topic=topic, _anchor=f"course-{topic}")


@app.route("/<topic>/curriculum")
def curriculum(topic: str) -> str:
    topic_dir = safe_path(app.config["ROOT"], topic)
    cur = topic_dir / "curriculum.md"
    if not cur.exists():
        abort(404)
    text = cur.read_text(encoding="utf-8")
    return render_template(
        "curriculum.html",
        topic_slug=topic,
        topic=parse_header((topic_dir / "README.md").read_text(encoding="utf-8")).get("topic", topic)
        if (topic_dir / "README.md").exists()
        else topic,
        curriculum_html=render_markdown(text),
        return_url=_support_return_url(topic),
    )


# 単一 md をそのまま表示する補助ページ（glossary / resources）
_ASSET_PAGES = {
    "glossary": {"file": "GLOSSARY.md", "kicker": "Glossary", "title": "用語集", "icon": "note"},
    "resources": {"file": "RESOURCES.md", "kicker": "Resources", "title": "資料室", "icon": "file"},
}


def _serve_asset(topic: str, key: str) -> str:
    cfg = _ASSET_PAGES[key]
    topic_dir = safe_path(app.config["ROOT"], topic)
    asset = topic_dir / cfg["file"]
    if not asset.exists():
        abort(404)
    text = asset.read_text(encoding="utf-8")
    readme = topic_dir / "README.md"
    topic_name = (
        parse_header(readme.read_text(encoding="utf-8")).get("topic", topic)
        if readme.exists()
        else topic
    )
    return render_template(
        "asset.html",
        topic_slug=topic,
        topic=topic_name,
        asset_key=key,
        kicker=cfg["kicker"],
        page_title=cfg["title"],
        kicker_icon=cfg["icon"],
        asset_html=render_markdown(text),
        return_url=_support_return_url(topic),
    )


@app.route("/<topic>/glossary")
def glossary(topic: str) -> str:
    return _serve_asset(topic, "glossary")


@app.route("/<topic>/resources")
def resources(topic: str) -> str:
    return _serve_asset(topic, "resources")


def _slug(s: str) -> str:
    """URL/HTML-friendly slug。Unicode 単語文字（日本語含む）は保持。"""
    s = re.sub(r"[\s/]+", "-", s.strip())
    s = re.sub(r"[^\w\-]", "", s, flags=re.UNICODE)
    return s.lower() or "part"


def _part_key(label: str) -> str:
    """`### Part B: Faded Example` と `### Part B` を同じキーに寄せる。
    コロン以降の説明文を捨ててから slug 化する。"""
    head = label.split(":", 1)[0].split("（", 1)[0]
    return _slug(head)


# Variant D の sub-question 検出パターン
_RE_BOLD_SUB = re.compile(r"^\*\*(Q\d+|課題\d+|問\d+|\d+)\.\s*\*\*", re.MULTILINE)
_RE_CODE_SUB = re.compile(r"^//\s*(課題\d+|Q\d+|問\d+)(?=[:：\s]|$)", re.MULTILINE)
_RE_FLAT_QMARK = re.compile(r"^(Q\d+|課題\d+|問\d+)[.。]", re.MULTILINE)
_RE_CODE_BLOCK = re.compile(r"```([^\n]*)\n(.*?)\n```", re.DOTALL)
_RE_ANSWER_SLOT = re.compile(
    r'^<!--\s*study-answer\s+top="([\w-]+)"\s+sub="([\w-]+)"(?:\s+top-heading="[^"\r\n]*"\s+sub-heading="[^"\r\n]*")?\s*-->\n?(.*?)\n?^<!--\s*/study-answer\s*-->$',
    re.MULTILINE | re.DOTALL,
)
_ANSWER_SLOT_END = "<!-- /study-answer -->"
_READONLY_HINTS = ("Worked Example", "読むだけ", "手は動かさなくてよい", "読んで理解")


def _detect_subparts(content_md: str, label: str) -> dict[str, Any]:
    """Part 内のサブ問題パターンを検出。
    Returns:
      {kind: 'read-only'}
      {kind: 'bold-split', intro_md, subs: [{label, label_id, content_md}]}
      {kind: 'code-split', intro_md, trailing_md, subs: [{label, label_id, code_md}]}
      {kind: 'flat'}
    """
    if any(k in label for k in _READONLY_HINTS) or any(k in content_md for k in _READONLY_HINTS):
        return {"kind": "read-only"}

    # 1. Bold-Q pattern（Part C 想定）
    bold = list(_RE_BOLD_SUB.finditer(content_md))
    if len(bold) >= 2:
        intro = content_md[: bold[0].start()].rstrip()
        subs = []
        for i, m in enumerate(bold):
            sl = m.group(1)
            end = bold[i + 1].start() if i + 1 < len(bold) else len(content_md)
            subs.append({
                "label": sl,
                "label_id": _slug(sl),
                "content_md": content_md[m.start():end].rstrip(),
            })
        return {"kind": "bold-split", "intro_md": intro, "subs": subs}

    # 2. Code-comment pattern（Part B 想定）— 最初の code block を分割
    for cm in _RE_CODE_BLOCK.finditer(content_md):
        lang = cm.group(1).strip()
        code = cm.group(2)
        tasks = list(_RE_CODE_SUB.finditer(code))
        if len(tasks) >= 2:
            pre_text = content_md[: cm.start()].rstrip()
            post_text = content_md[cm.end():].strip()
            subs = []
            for i, tm in enumerate(tasks):
                sl = tm.group(1)
                end = tasks[i + 1].start() if i + 1 < len(tasks) else len(code)
                chunk = code[tm.start():end].rstrip()
                subs.append({
                    "label": sl,
                    "label_id": _slug(sl),
                    "code_md": f"```{lang}\n{chunk}\n```",
                })
            return {
                "kind": "code-split",
                "intro_md": pre_text,
                "trailing_md": post_text,
                "subs": subs,
            }

    return {"kind": "flat"}


def split_body_parts(body_text: str) -> list[dict[str, Any]]:
    """body_text を分解。`## 課題` / `## 問題` セクション内の `### Part X` を part として扱う。
    課題セクションの手前にあるイントロ（学習目標・前提知識・アナロジー解説）は全部 intro 1ブロック。
    `## 課題` 自体が無いか `### ` が無い場合は body 全体を1つの flat part として返す。"""
    # まず `## 課題` または `## 問題` を探す
    q_match = re.search(r"^##\s+(課題|問題)\b", body_text, re.MULTILINE)
    if q_match:
        intro_md = body_text[: q_match.start()].rstrip()
        questions_md = body_text[q_match.start():]
    else:
        intro_md = ""
        questions_md = body_text

    matches = list(re.finditer(r"^### (.+)$", questions_md, re.MULTILINE))
    parts: list[dict[str, Any]] = []
    if intro_md.strip():
        parts.append({"kind": "intro", "content_md": intro_md})

    if not matches:
        # `### Part X` が無い → questions_md 全体を1つの flat part
        sub_info = _detect_subparts(questions_md, "")
        parts.append({
            "kind": "part",
            "label": "回答",
            "label_id": "main",
            "content_md": questions_md.strip(),
            "body_only_md": questions_md.strip(),
            "sub_info": sub_info,
            "answer_style": "code" if sub_info.get("kind") == "code-split" or _RE_CODE_BLOCK.search(questions_md) else "text",
        })
        return parts

    # `## 課題` の見出しと、最初の `### ` までの導入文（あれば intro 末尾に追加）
    qh_end = re.search(r"\n", questions_md).end() if re.search(r"\n", questions_md) else 0
    pre_first = questions_md[qh_end: matches[0].start()].rstrip()
    if pre_first.strip():
        # intro があれば追記、無ければ新規 intro
        if parts and parts[-1]["kind"] == "intro":
            parts[-1]["content_md"] += "\n\n" + pre_first
        else:
            parts.append({"kind": "intro", "content_md": pre_first})

    for i, m in enumerate(matches):
        label = m.group(1).strip()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(questions_md)
        section_md = questions_md[m.start():end].rstrip()
        body_only = re.sub(r"^### .+\n?", "", section_md, count=1)
        sub_info = _detect_subparts(body_only, label)
        parts.append({
            "kind": "part",
            "label": label,
            "label_id": _part_key(label),
            "content_md": section_md,
            "body_only_md": body_only,
            "sub_info": sub_info,
            "answer_style": "code" if sub_info.get("kind") == "code-split" or _RE_CODE_BLOCK.search(body_only) else "text",
        })
    return parts


_RE_HINT_DETAILS = re.compile(
    r"<details\b[^>]*>\s*<summary\b[^>]*>(.*?)</summary>\s*(.*?)\s*</details>",
    re.IGNORECASE | re.DOTALL,
)
_RE_HINT_PART = re.compile(r"\bPart\s+([A-Za-z0-9]+)\b", re.IGNORECASE)
_RE_HINT_PART_PREFIX = re.compile(
    r"^\s*(?:[-*]\s*)?Part\s+([A-Za-z0-9]+)(?=\s|[:：]|は|の|$)",
    re.IGNORECASE,
)


def assign_hints_to_parts(parts: list[dict[str, Any]], hints_text: str) -> None:
    """Markdownのヒントを対応する回答課題へ割り当てる。

    Generatorの既存形式では、1つのdetails内に ``Part B: ...`` と
    ``Part C: ...`` が混在する。参照先が明示された行以降をそのPartへ
    寄せ、Part指定のない従来形式は全回答課題から参照できるようにする。
    """
    actionable = [
        part
        for part in parts
        if part.get("kind") == "part" and part.get("sub_info", {}).get("kind") != "read-only"
    ]
    valid_keys = {part["label_id"] for part in actionable}
    grouped: dict[str, list[tuple[str, str]]] = {key: [] for key in valid_keys}
    if not actionable or not hints_text.strip():
        return

    blocks = list(_RE_HINT_DETAILS.finditer(hints_text))
    if not blocks:
        fallback = re.sub(r"(?m)^##\s*ヒント\s*$", "", hints_text)
        fallback = re.sub(r"(?m)^---\s*$", "", fallback).strip()
        if fallback:
            rendered = render_markdown(fallback)
            for part in actionable:
                part["hint_html"] = rendered
        return

    def append_common(text: str) -> None:
        text = re.sub(r"(?m)^##\s*ヒント\s*$", "", text)
        text = re.sub(r"(?m)^---\s*$", "", text).strip()
        if text:
            for key in valid_keys:
                grouped[key].append(("", text))

    cursor = 0
    for block in blocks:
        append_common(hints_text[cursor:block.start()])
        summary = re.sub(r"<[^>]+>", "", block.group(1)).strip()
        body = block.group(2).strip()
        summary_matches = list(_RE_HINT_PART.finditer(summary))
        summary_targets = {
            _part_key(f"Part {match.group(1)}")
            for match in summary_matches
        } & valid_keys
        current_targets = summary_targets if summary_matches else set(valid_keys)
        lines_by_target: dict[str, list[str]] = {key: [] for key in valid_keys}
        active_fence: tuple[str, int] | None = None

        for line in body.splitlines():
            target_match = None
            fence_match = re.match(r"^(`{3,}|~{3,})", line)
            if fence_match:
                fence = fence_match.group(1)
                marker = fence[0]
                if active_fence is None:
                    active_fence = (marker, len(fence))
                elif (
                    active_fence[0] == marker
                    and len(fence) >= active_fence[1]
                    and not line[fence_match.end():].strip()
                ):
                    active_fence = None
            elif active_fence is None:
                target_match = _RE_HINT_PART_PREFIX.match(line)
                if target_match:
                    current_targets = {
                        _part_key(f"Part {target_match.group(1)}")
                    } & valid_keys
            cleaned = line
            if active_fence is None and target_match:
                cleaned = re.sub(
                    r"^(\s*[-*]\s*)Part\s+[A-Za-z0-9]+\s*[:：]\s*",
                    r"\1",
                    line,
                    count=1,
                    flags=re.IGNORECASE,
                )
            for target in current_targets:
                lines_by_target[target].append(cleaned)

        for target, lines in lines_by_target.items():
            content = "\n".join(lines).strip()
            if content:
                grouped[target].append((summary, content))
        cursor = block.end()

    append_common(hints_text[cursor:])
    for part in actionable:
        blocks_md = [
            f"**{summary}**\n\n{content}" if summary else content
            for summary, content in grouped.get(part["label_id"], [])
        ]
        if blocks_md:
            part["hint_html"] = render_markdown("\n\n".join(blocks_md))


def split_answer_parts(answer_text: str) -> tuple[dict[str, dict[str, str]], str]:
    """既存の回答テキストを ### top / sub-marker 単位で分解。
    Returns:
      ({top_id: {sub_id_or_'_flat': text, ...}, ...}, trailing_text)
    trailing_text は ### Part X に属さない末尾セクション（例: `###質問`）。"""
    result: dict[str, dict[str, str]] = {}
    trailing = ""
    slots = list(_RE_ANSWER_SLOT.finditer(answer_text))
    if slots:
        for slot in slots:
            top_id, sub_id, content = slot.groups()
            # The serializer adds one delimiter newline on each side. Remove
            # only those delimiters, leaving the learner's indentation and
            # intentional leading/trailing newlines untouched.
            if content.startswith("\n"):
                content = content[1:]
            if content.endswith("\n"):
                content = content[:-1]
            result.setdefault(top_id, {})[sub_id] = _unescape_answer_slot(content)
        without_slots = _RE_ANSWER_SLOT.sub("", answer_text)
        trailing = re.sub(r"^### [^\n]+\n?", "", without_slots, flags=re.MULTILINE).strip()
        return result, trailing
    return _split_legacy_answer_parts(answer_text)


def _unescape_answer_slot(content: str) -> str:
    """Reverse the browser's collision-safe slot encoding without trimming."""
    output: list[str] = []
    index = 0
    while index < len(content):
        if content.startswith("\\M", index):
            output.append(_ANSWER_SLOT_END)
            index += 2
        elif content.startswith("\\\\", index):
            output.append("\\")
            index += 2
        else:
            output.append(content[index])
            index += 1
    return "".join(output)


def _split_legacy_answer_parts(answer_text: str) -> tuple[dict[str, dict[str, str]], str]:
    """スロットマーカー導入前の見出しベース回答を読み取る。"""
    result: dict[str, dict[str, str]] = {}
    trailing = ""

    # ### Part X / ### Part Y を見つける（### がスペースなしのものは末尾扱い）
    top_matches = list(re.finditer(r"^### ([^#\n].*)$", answer_text, re.MULTILINE))
    if not top_matches:
        if answer_text.strip():
            result["main"] = {"_flat": answer_text.strip()}
        return result, ""

    for i, m in enumerate(top_matches):
        top_label = m.group(1).strip()
        top_id = _part_key(top_label)
        end = top_matches[i + 1].start() if i + 1 < len(top_matches) else len(answer_text)
        body = answer_text[m.end():end]

        # この top の中に「###（スペースなし）xxx」のような trailing がある場合、そこで切る
        trail_m = re.search(r"\n###(?!#)(?=\S)", body)
        if trail_m:
            trailing = (trailing + "\n" + body[trail_m.start():].strip()).strip()
            body = body[: trail_m.start()]
        body = body.strip()

        sub_dict: dict[str, str] = {}
        # `#### subname` markers
        sharp_subs = list(re.finditer(r"^#### (.+)$", body, re.MULTILINE))
        if sharp_subs:
            if sharp_subs[0].start() > 0:
                pre = body[: sharp_subs[0].start()].strip()
                if pre:
                    sub_dict["_flat"] = pre
            for j, sm in enumerate(sharp_subs):
                sl = sm.group(1).strip()
                send = sharp_subs[j + 1].start() if j + 1 < len(sharp_subs) else len(body)
                sub_dict[_slug(sl)] = body[sm.end():send].strip()
        else:
            # `Q1.` / `課題1.` line markers
            q_matches = list(_RE_FLAT_QMARK.finditer(body))
            if q_matches:
                if q_matches[0].start() > 0:
                    pre = body[: q_matches[0].start()].strip()
                    if pre:
                        sub_dict["_flat"] = pre
                for j, qm in enumerate(q_matches):
                    sl = qm.group(1)
                    qend = q_matches[j + 1].start() if j + 1 < len(q_matches) else len(body)
                    text = body[qm.end():qend]
                    text = re.sub(r"^[.。\s　]+", "", text).strip()
                    sub_dict[_slug(sl)] = text
            elif body:
                sub_dict["_flat"] = body

        # `_flat` 内が単一の code block で `// 課題N` などで分かれている場合、サブに割る
        if sub_dict.get("_flat") and len(sub_dict) == 1:
            flat = sub_dict["_flat"]
            cm = re.match(r"^```([^\n]*)\n(.*)\n```\s*$", flat.strip(), re.DOTALL)
            if cm:
                lang = cm.group(1).strip()
                code = cm.group(2)
                tasks = list(_RE_CODE_SUB.finditer(code))
                if len(tasks) >= 2:
                    sub_dict.pop("_flat")
                    for j, tm in enumerate(tasks):
                        sl = tm.group(1)
                        tend = tasks[j + 1].start() if j + 1 < len(tasks) else len(code)
                        chunk = code[tm.start():tend].rstrip()
                        sub_dict[_slug(sl)] = f"```{lang}\n{chunk}\n```"
            else:
                tasks = list(_RE_CODE_SUB.finditer(flat))
                if len(tasks) >= 2:
                    sub_dict.pop("_flat")
                    for j, tm in enumerate(tasks):
                        sl = tm.group(1)
                        tend = tasks[j + 1].start() if j + 1 < len(tasks) else len(flat)
                        sub_dict[_slug(sl)] = flat[tm.start():tend].rstrip()

        result[top_id] = sub_dict

    return result, trailing.strip()


def _is_grade_placeholder(text: str) -> bool:
    """採点前のプレースホルダ（空 or `_未採点_`）かどうか。"""
    s = (text or "").strip()
    return not s or s == "_未採点_"


def _split_by_part_headers(section_body: str) -> tuple[str, dict[str, str]]:
    """`## 解説` / `## 模範回答` の本文を `### <label>` 単位に分割。
    Returns (最初の見出しより前の本文, {part_key: 本文})。
    `### ` が無ければ (本文全体, {}) を返す。part_key は body 側の `### Part X` と
    同じ正規化（_part_key）なので、課題ごとの解答欄に対応付けできる。"""
    if _is_grade_placeholder(section_body):
        return "", {}
    matches = list(re.finditer(r"^### (.+)$", section_body, re.MULTILINE))
    if not matches:
        return section_body.strip(), {}
    pre = section_body[: matches[0].start()].strip()
    by: dict[str, str] = {}
    for i, m in enumerate(matches):
        label = m.group(1).strip()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section_body)
        by[_part_key(label)] = section_body[m.end():end].strip()
    return pre, by


def split_grading(grading_text: str) -> dict[str, Any]:
    """`## 採点` / `## 解説` / `## 模範回答` を構造化する。
    解説・模範回答は課題（### Part X）ごとに分割し、解答欄の直下に表示できるようにする。
    課題に紐付かない総評や、課題で分かれていない旧形式は呼び出し側で下部にまとめる。"""
    score_md = _section_body(grading_text, "## 採点").strip()
    expl_section = _section_body(grading_text, "## 解説")
    model_section = _section_body(grading_text, "## 模範回答")
    if not model_section.strip():
        # `模範解答` 表記ゆれにも対応
        model_section = _section_body(grading_text, "## 模範解答")
    expl_pre, expl_by = _split_by_part_headers(expl_section)
    model_pre, model_by = _split_by_part_headers(model_section)
    return {
        "score_md": "" if _is_grade_placeholder(score_md) else score_md,
        "expl_full": "" if _is_grade_placeholder(expl_section) else expl_section.strip(),
        "expl_pre": expl_pre,
        "expl_by": expl_by,
        "model_full": "" if _is_grade_placeholder(model_section) else model_section.strip(),
        "model_pre": model_pre,
        "model_by": model_by,
    }


def assign_grading_to_parts(
    body_parts: list[dict[str, Any]], grading: dict[str, Any]
) -> str:
    """grading の 解説・模範回答 を body_parts の各 part に割り当て（破壊的に expl_md/model_md を追加）。
    課題に紐付かなかった分は下部ブロック用の markdown 文字列として返す。"""
    gradable = [
        p
        for p in body_parts
        if p.get("kind") == "part" and p.get("sub_info", {}).get("kind") != "read-only"
    ]
    leftover_expl = ""
    leftover_model = ""

    if len(gradable) == 1:
        # 単一課題（診断問題・flat lesson 等）: 解説/模範回答は丸ごとその課題に付ける
        gradable[0]["expl_md"] = grading["expl_full"]
        gradable[0]["model_md"] = grading["model_full"]
    elif gradable:
        matched: set[str] = set()
        for p in gradable:
            e = grading["expl_by"].get(p["label_id"], "")
            m = grading["model_by"].get(p["label_id"], "")
            if e or m:
                matched.add(p["label_id"])
            p["expl_md"] = e
            p["model_md"] = m
        leftover_expl = "\n\n".join(
            x
            for x in [grading["expl_pre"]]
            + [v for k, v in grading["expl_by"].items() if k not in matched]
            if x
        ).strip()
        leftover_model = "\n\n".join(
            x
            for x in [grading["model_pre"]]
            + [v for k, v in grading["model_by"].items() if k not in matched]
            if x
        ).strip()
    else:
        # 採点対象 part が無い（read-only のみ等）: 全部下部へ
        leftover_expl = grading["expl_full"]
        leftover_model = grading["model_full"]

    bottom_blocks: list[str] = []
    if grading["score_md"]:
        bottom_blocks.append("## 採点\n\n" + grading["score_md"])
    if leftover_expl:
        bottom_blocks.append("## 解説\n\n" + leftover_expl)
    if leftover_model:
        bottom_blocks.append("## 模範回答\n\n" + leftover_model)
    return "\n\n".join(bottom_blocks)


def _serve_lesson(topic: str, kind: str, name: str) -> str:
    topic_dir = safe_path(app.config["ROOT"], topic)
    file_path = safe_path(topic_dir, kind, name)
    if not file_path.exists() or file_path.suffix != ".md":
        abort(404)
    text = file_path.read_text(encoding="utf-8")
    headers = parse_header(text)
    files = list_files(topic_dir, kind)
    current_idx = next(
        (i for i, f in enumerate(files) if f["name"] == name), None
    )
    prev_file = files[current_idx - 1] if current_idx is not None and current_idx > 0 else None
    next_file = (
        files[current_idx + 1]
        if current_idx is not None and current_idx + 1 < len(files)
        else None
    )

    # md を3パートに分割: 課題本文（## 回答欄 まで） / ヒント / 採点・解説・模範回答
    body_text, hints_text, grading_text = _split_lesson(text)
    meta_line = _extract_meta_line(text)
    lesson_body = re.sub(r"(?m)^#\s+.+\n?", "", body_text, count=1)
    if meta_line:
        lesson_body = lesson_body.replace(meta_line, "", 1)
    learning_goal_md = _section_body(lesson_body, "## 学習目標").strip()
    lesson_body = re.sub(
        r"(?ms)^##\s*学習目標\s*\n.*?(?=^##\s|\Z)",
        "",
        lesson_body,
        count=1,
    ).strip()

    # body を ### Part 単位で分解 + サブ問題検出（read-only / bold-split / code-split / flat）。
    # 既存回答も ### / #### / Q マーカーで分解し、対応する textarea に pre-fill する。
    answer_text = extract_answer(text)
    body_parts = split_body_parts(lesson_body)
    assign_hints_to_parts(body_parts, hints_text)
    answer_parts, answer_trailing = split_answer_parts(answer_text)

    # 採点済みなら 解説・模範回答 を課題ごとに割り当て、各課題の解答欄直下に表示する。
    # 課題に紐付かない総評・旧形式（課題で分かれていない採点）は下部ブロックにまとめる。
    # 未採点のうちは従来どおり下部に折りたたんで置く（`_未採点_` 表示）。
    graded_flag = is_graded(text)
    if grading_text and graded_flag:
        # assign_grading_to_parts が body_parts に expl_md/model_md を付与しつつ
        # 課題に紐付かなかった分を下部用 markdown として返す
        bottom_md = assign_grading_to_parts(body_parts, split_grading(grading_text))
        grading_bottom_html = render_markdown(bottom_md) if bottom_md else ""
    elif grading_text:
        grading_bottom_html = render_markdown(grading_text)
    else:
        grading_bottom_html = ""

    # 左ペインの一覧表示用
    sidebar_diagnostic = list_files(topic_dir, "diagnostic")
    sidebar_lessons = list_files(topic_dir, "lessons")
    session = next((item for item in list_sessions() if item["slug"] == topic), None)
    overview = learning_overview(session) if session else None
    score = extract_score(text)
    feedback = score_feedback(score)
    task_total = sum(
        1
        for part in body_parts
        if part.get("kind") == "part" and part.get("sub_info", {}).get("kind") != "read-only"
    )

    return render_template(
        "lesson.html",
        topic_slug=topic,
        kind=kind,
        name=name,
        title=re.search(r"^#\s+(.+)$", text, re.MULTILINE).group(1)
        if re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        else name,
        meta_line=meta_line,
        learning_goal_html=render_markdown(learning_goal_md) if learning_goal_md else "",
        body_html=render_markdown(body_text),
        grading_html=grading_bottom_html,
        answer=answer_text,
        body_parts=body_parts,
        answer_parts=answer_parts,
        answer_trailing=answer_trailing,
        graded=is_graded(text),
        score=score,
        feedback=feedback,
        task_total=task_total,
        prev_file=prev_file,
        next_file=next_file,
        sidebar_diagnostic=sidebar_diagnostic,
        sidebar_lessons=sidebar_lessons,
        topic=parse_header((topic_dir / "README.md").read_text(encoding="utf-8")).get("topic", topic)
        if (topic_dir / "README.md").exists()
        else topic,
        overview=overview,
    )


@app.route("/<topic>/diagnostic/<name>")
def diagnostic_view(topic: str, name: str) -> str:
    return _serve_lesson(topic, "diagnostic", name)


@app.route("/<topic>/lessons/<name>")
def lesson_view(topic: str, name: str) -> str:
    return _serve_lesson(topic, "lessons", name)


@app.route("/<topic>/<kind>/<name>/confirmation")
def answer_confirmation(topic: str, kind: str, name: str) -> Any:
    if kind not in {"diagnostic", "lessons"}:
        abort(404)
    try:
        _, record = _confirmation_record(request.args.get("token"))
    except ValueError:
        abort(410)
    if record.get("topic") != topic or record.get("kind") != kind or record.get("name") != name:
        abort(404)
    file_path = Path(str(record["path"]))
    text = file_path.read_text(encoding="utf-8")
    target_endpoint = "diagnostic_view" if kind == "diagnostic" else "lesson_view"
    return render_template(
        "answer_confirmation.html",
        topic_slug=topic,
        kind=kind,
        name=name,
        answer=extract_answer(text),
        graded=is_graded(text),
        confirmation_token=request.args.get("token"),
        feedback_tags=record.get("tags", []),
        feedback_note=record.get("note", ""),
        back_url=url_for(target_endpoint, topic=topic, name=name),
    )


# ---------- FEEDBACK.md handling ----------

# 採点 Agent が読み書きするセッション固有のフィードバック蓄積ファイル。grill-me で決定:
# - YAML frontmatter (rules) + Markdown body (エビデンスログ)
# - 提出時にエビデンスログ append のみ（Critic は採点フローで起動）
# - ルール更新は採点 Agent が Critic 経由で提案、新規は自動、既存変更は chat で承認

FEEDBACK_TEMPLATE = """---
schema_version: 1
rules: []
---

# FEEDBACK.md

このトピック学習中にユーザーから受け取った FB を蓄積するファイル。

- 上の YAML `rules` は採点 Agent (Critic) が抽出した「次回以降必読の方針」。Generator/Critic は必ず読む。
- 下のエビデンスログはユーザーの submit ごとに append される生 FB。Critic がルール抽出時の根拠とする。
- 新規ルールは採点中に自動追記。既存ルールの変更・削除は Claude Code chat でユーザーに承認を取る。
- ユーザーの Profile (Strong/Weak) は README.md 側で別管理。両方を併読すること。

## エビデンスログ
"""


def _ensure_feedback_md(topic_dir: Path) -> Path:
    """FEEDBACK.md が無ければ初期テンプレで作成し、Path を返す。"""
    fb = topic_dir / "FEEDBACK.md"
    if not fb.exists():
        atomic_write(fb, FEEDBACK_TEMPLATE)
    return fb


def _next_log_id(text: str, date_str: str) -> str:
    """既存ログ内で同日の log-YYYY-MM-DD-NNN を数えて次の連番を返す。"""
    prefix = f"log-{date_str}-"
    nums: list[int] = []
    for m in re.finditer(rf"###\s+{re.escape(prefix)}(\d+)\b", text):
        try:
            nums.append(int(m.group(1)))
        except ValueError:
            pass
    next_n = (max(nums) + 1) if nums else 1
    return f"{prefix}{next_n:03d}"


def append_feedback_log(
    topic_dir: Path,
    *,
    kind: str,
    name: str,
    tags: list[str],
    note: str,
) -> str | None:
    """FB ログを FEEDBACK.md のエビデンスログに append。
    tags も note も空なら何もせず None を返す。append したら log id を返す。"""
    tags = [t.strip() for t in tags if t and t.strip()]
    note = (note or "").strip()
    if not tags and not note:
        return None

    fb_path = _ensure_feedback_md(topic_dir)
    current = fb_path.read_text(encoding="utf-8")
    now = datetime.now().astimezone()
    date_str = now.strftime("%Y-%m-%d")
    log_id = _next_log_id(current, date_str)

    target = f"{kind}/{name}"
    tags_md = ", ".join(f"`{t}`" for t in tags) if tags else "(なし)"
    note_block = note if note else "(なし)"

    entry = (
        f"\n### {log_id} — {target}\n"
        f"\n- **submitted**: {now.isoformat(timespec='seconds')}"
        f"\n- **tags**: {tags_md}"
        f"\n- **note**:\n\n"
        f"  > {note_block.replace(chr(10), chr(10) + '  > ')}\n"
        f"\n- **critic_state**: pending\n"
    )

    if current.endswith("\n"):
        new_content = current + entry
    else:
        new_content = current + "\n" + entry
    atomic_write(fb_path, new_content)
    return log_id


# ---------- Submission ----------


def _submit(topic: str, kind: str, name: str) -> Any:
    require_csrf()
    topic_dir = safe_path(app.config["ROOT"], topic)
    file_path = safe_path(topic_dir, kind, name)
    if not file_path.exists():
        abort(404)
    with session_lock(topic_dir):
        text = file_path.read_text(encoding="utf-8")
        new_answer = request.form.get("answer", "")
        new_text = replace_answer(text, new_answer)
        atomic_write(file_path, new_text)

        # FB タグ・自由記述があれば FEEDBACK.md のエビデンスログに追記
        fb_tags = request.form.getlist("fb_tags")
        fb_note = request.form.get("fb_note", "")
        cleaned_tags = [tag.strip() for tag in fb_tags if tag and tag.strip()]
        try:
            append_feedback_log(topic_dir, kind=kind, name=name, tags=fb_tags, note=fb_note)
        except OSError:
            # FEEDBACK.md 書込み失敗は提出を阻害しない（ベストエフォート）
            pass
        confirmation_token = _new_confirmation(topic, kind, name, file_path, new_answer, cleaned_tags, fb_note)

    return redirect(url_for("answer_confirmation", topic=topic, kind=kind, name=name, token=confirmation_token))


@app.route("/<topic>/diagnostic/<name>/submit", methods=["POST"])
def diagnostic_submit(topic: str, name: str) -> Any:
    return _submit(topic, "diagnostic", name)


@app.route("/<topic>/lessons/<name>/submit", methods=["POST"])
def lessons_submit(topic: str, name: str) -> Any:
    return _submit(topic, "lessons", name)


# url_for エンドポイント名と一致させるためのエイリアス
app.view_functions["lesson_view"] = lesson_view


# ---------- Section split helpers ----------


def _split_lesson(text: str) -> tuple[str, str, str]:
    """lesson md を 3パートに分割。
    - body: 先頭〜`## 回答欄` セクション末まで（フォーム前）
    - hints: `## ヒント` セクション
    - grading: `## 採点` 以降
    """
    # 採点以降
    grading_match = re.search(r"(?m)^##\s*採点", text)
    grading_text = text[grading_match.start():] if grading_match else ""
    pre_grading = text[: grading_match.start()] if grading_match else text

    # ヒント
    hints_match = re.search(r"(?m)^##\s*ヒント", pre_grading)
    if hints_match:
        body_text = pre_grading[: hints_match.start()]
        hints_text = pre_grading[hints_match.start():]
    else:
        body_text = pre_grading
        hints_text = ""

    # 採点側からは `---` 区切りを取り除く
    grading_text = re.sub(r"^---\s*\n", "", grading_text, count=1, flags=re.MULTILINE)

    # body から `## 回答欄` セクションを除く（フォームに置き換える前提）
    body_text = re.sub(
        r"(?ms)^##\s*回答欄.*?(?=^---\s*$|^##\s|\Z)",
        "",
        body_text,
        count=1,
    )
    body_text = re.sub(r"\n---\s*\n", "\n", body_text)
    return body_text.rstrip() + "\n", hints_text, grading_text


def _extract_meta_line(text: str) -> str:
    """`# Title` 直下の `Level X / bloom / type / Stage Y` ラインを抽出。"""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            for j in range(i + 1, min(i + 5, len(lines))):
                stripped = lines[j].strip()
                if stripped and not stripped.startswith("#"):
                    return stripped
            break
    return ""


# ---------- Entrypoint ----------


def main() -> int:
    ap = argparse.ArgumentParser(description="Study Loop Web UI server")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument(
        "--backend",
        choices=("auto", "codex", "manual"),
        default=os.environ.get("STUDY_LOOP_BACKEND", "auto"),
        help="Codex 連携の既定（auto/codex/manual、デフォルト: auto）",
    )
    ap.add_argument(
        "--root",
        default=".study",
        help="Study Loop セッションディレクトリのパス（デフォルト: ./.study）",
    )
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    if not _is_loopback_host(args.host):
        ap.error("--host は 127.0.0.1、localhost、または ::1 にしてください")

    root = Path(args.root).expanduser().resolve()
    if not root.exists():
        print(
            f"WARN: {root} がまだ存在しません。Claude Code でセッション開始後に再起動してください。",
            file=sys.stderr,
        )
    app.config["ROOT"] = root
    app.config["PROJECT_ROOT"] = root.parent
    app.config["BACKEND"] = args.backend
    print(f"Study Loop Web UI on http://{args.host}:{args.port}  (root: {root})")
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
