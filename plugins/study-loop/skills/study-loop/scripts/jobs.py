"""Safe in-memory, FIFO Codex jobs for the local Study Loop UI."""

from __future__ import annotations

import json
import hashlib
import queue
import re
import shlex
import threading
import uuid
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, ContextManager

from codex_app_server import AppServerError, AppServerStatus, CodexAppServerClient


ALLOWED_ACTIONS = frozenset({
    "session_start", "diagnostic_grade", "diagnostic_accept", "curriculum_revise",
    "curriculum_accept", "lesson_grade", "spaced_review", "session_end",
})
JOB_STATUSES = frozenset({"queued", "running", "waiting_input", "waiting_approval", "completed", "failed", "cancelled"})
PHASES = frozenset({"preparing", "confirming", "grading", "updating"})
RESULT_KEYS = frozenset({"status", "summary", "resultPath", "nextAction"})
NEXT_ACTIONS = frozenset({"answer", "review_curriculum", "retry_or_continue", "done", None})
SYSTEM_SHELL_WRAPPERS = frozenset({"/bin/zsh", "/bin/sh"})
APPLY_PATCH_MAX_BYTES = 64 * 1024
REQUEST_METHODS = frozenset({
    "item/tool/requestUserInput",
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval",
    "item/permissions/requestApproval",
})
RequestId = str | int


@dataclass
class JobEvent:
    id: int
    kind: str
    data: dict[str, Any]


@dataclass
class Job:
    id: str
    action: str
    topic: str
    payload: dict[str, Any]
    status: str = "queued"
    phase: str = "preparing"
    message: str = "準備中です。"
    result: dict[str, Any] | None = None
    error: str | None = None
    thread_id: str | None = None
    turn_id: str | None = None
    pending_request_id: RequestId | None = None
    pending_kind: str | None = None
    pending_details: dict[str, Any] | None = None
    events: list[JobEvent] = field(default_factory=list)
    next_event_id: int = 1
    done: threading.Event = field(default_factory=threading.Event)
    agent_text: str = ""
    # Codex 0.144.3 emits the completed agent-message item after its text
    # deltas. The completed item is authoritative; deltas remain a fallback
    # for older servers that do not emit it.
    final_agent_text: str | None = None
    final_agent_item_id: str | None = None
    agent_text_by_item: dict[str, str] = field(default_factory=dict)
    early_notifications: list[dict[str, Any]] = field(default_factory=list)
    early_requests: list[dict[str, Any]] = field(default_factory=list)
    cancel_requested: bool = False
    failure_pending: bool = False
    interrupt_key: tuple[int, str, str] | None = None
    cancel_timer: threading.Timer | None = field(default=None, repr=False)
    resolution_reserved: bool = False
    resolution_consumed: bool = False
    workflow_snapshot: Any = field(default=None, repr=False)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id, "status": self.status, "topic": self.topic, "action": self.action,
            "phase": self.phase, "message": self.message, "result": self.result, "error": self.error,
            "waiting": self.pending_kind, "details": self.pending_details,
        }


def _phase_for(action: str) -> str:
    if action in {"diagnostic_grade", "lesson_grade"}:
        return "grading"
    if action in {"diagnostic_accept", "curriculum_revise", "curriculum_accept", "session_end"}:
        return "updating"
    return "preparing"


def _short(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()[:240]


def _request_text(value: Any, *, limit: int = 16_384) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError("Codex CLI 0.144.3 互換性エラー: 承認内容が不正です。")
    return value


def _validate_result(value: Any, project_root: Path, topic: str, action: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != RESULT_KEYS:
        raise ValueError("Codex の最終結果が指定形式ではありません。")
    if value.get("status") != "completed" or not isinstance(value.get("summary"), str):
        raise ValueError("Codex の最終結果が完了形式ではありません。")
    if value.get("nextAction") not in NEXT_ACTIONS:
        raise ValueError("Codex の次の操作が不正です。")
    result_path = value.get("resultPath")
    if result_path is not None:
        if not isinstance(result_path, str) or not result_path.startswith(".study/"):
            raise ValueError("Codex の成果物パスが学習ディレクトリ外です。")
        parts = Path(result_path).parts
        if len(parts) < 3 or parts[:2] != (".study", topic):
            raise ValueError("Codex の成果物パスがこの学習セッションに一致しません。")
        raw_candidate = project_root / result_path
        topic_root = project_root / ".study" / topic
        if _contains_symlink_component(project_root, parts):
            raise ValueError("Codex の成果物パスにシンボリックリンクは使えません。")
        try:
            candidate = raw_candidate.resolve(strict=True)
            resolved_topic = topic_root.resolve(strict=True)
        except OSError as exc:
            raise ValueError("Codex の成果物ファイルが見つかりません。") from exc
        if raw_candidate.is_symlink() or not raw_candidate.is_file() or candidate.suffix != ".md" or (resolved_topic not in candidate.parents and candidate != resolved_topic):
            raise ValueError("Codex の成果物パスが学習ディレクトリ外です。")
        if not _result_kind_matches(parts[2:], action):
            raise ValueError("Codex の成果物種別がこの操作に一致しません。")
    return {"status": "completed", "summary": _short(value["summary"]), "resultPath": result_path, "nextAction": value["nextAction"]}


def _has_exact_result_keys(text: str) -> bool:
    """Recognize a completed-message candidate without trusting its values yet."""
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return False
    return isinstance(value, dict) and set(value) == RESULT_KEYS


def _completed_agent_result(item: Any) -> tuple[str, str] | None:
    """Return a schema-shaped final result from a completed agent-message item."""
    if not isinstance(item, dict) or item.get("type") != "agentMessage":
        return None
    item_id = item.get("id")
    text = item.get("text")
    phase = item.get("phase")
    if not isinstance(item_id, str) or not isinstance(text, str):
        return None
    if phase not in {None, "final_answer"} or not _has_exact_result_keys(text):
        return None
    return item_id, text


def _final_result_from_turn_items(items: Any) -> tuple[str, str] | None:
    """Use an embedded terminal item only when the separate notification was lost."""
    if not isinstance(items, list):
        return None
    unknown_phase: tuple[str, str] | None = None
    final_phase: tuple[str, str] | None = None
    for item in items:
        candidate = _completed_agent_result(item)
        if candidate is None:
            continue
        if isinstance(item, dict) and item.get("phase") == "final_answer":
            final_phase = candidate
        else:
            unknown_phase = candidate
    return final_phase or unknown_phase


def _contains_symlink_component(root: Path, parts: tuple[str, ...]) -> bool:
    """Reject a result when ``.study``, topic, or any child is a symlink."""
    current = root
    for part in parts:
        current = current / part
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
    return False


def _result_kind_matches(parts: tuple[str, ...], action: str) -> bool:
    if action in {"session_start", "diagnostic_grade"}:
        return len(parts) >= 2 and parts[0] == "diagnostic"
    if action in {"curriculum_accept", "spaced_review", "lesson_grade"}:
        return len(parts) >= 2 and parts[0] == "lessons"
    if action in {"diagnostic_accept", "curriculum_revise"}:
        return parts == ("curriculum.md",) or parts == ("RESOURCES.md",)
    if action == "session_end":
        return parts == ("README.md",)
    return False


class JobManager:
    """One worker, fixed operations, and no persistence outside Markdown."""

    def __init__(
        self,
        *,
        project_root: Path,
        client_factory: Callable[[], CodexAppServerClient],
        topic_lock: Callable[[str], ContextManager[Any]] | None = None,
        cancel_timeout_seconds: float = 10.0,
        preflight: Callable[[str, str, dict[str, Any]], None] | None = None,
        snapshot_workflow: Callable[[str], Any] | None = None,
        postflight: Callable[[str, str, dict[str, Any], dict[str, Any], Any], None] | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self._client_factory = client_factory
        self._topic_lock = topic_lock or (lambda _topic: nullcontext())
        self._cancel_timeout_seconds = cancel_timeout_seconds
        self._preflight = preflight
        self._snapshot_workflow = snapshot_workflow
        self._postflight = postflight
        self._jobs: dict[str, Job] = {}
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._lock = threading.RLock()
        self._client: CodexAppServerClient | None = None
        # Freeze safe commands once, before a turn can observe an untrusted
        # project PATH or any shell startup files.
        self._approved_executables = CodexAppServerClient._resolve_approved_executables()
        # The App Server resolves Codex Desktop's transient apply_patch
        # launcher while creating each turn.  Until then, no write command is
        # eligible for browser approval.
        self._apply_patch_launcher: Path | None = None
        self._active_id: str | None = None
        self._client_generation = 0
        self._closed = False
        self.last_connection_status: AppServerStatus | None = None
        self._worker = threading.Thread(target=self._work, name="study-loop-codex-worker", daemon=True)
        self._worker.start()

    def create_job(self, action: str, topic: str, payload: dict[str, Any]) -> Job:
        if action not in ALLOWED_ACTIONS:
            raise ValueError("許可されていない操作です。")
        if not re.fullmatch(r"[\w-]{1,120}", topic, flags=re.UNICODE) or not isinstance(payload, dict):
            raise ValueError("操作データが不正です。")
        with self._lock:
            for existing in self._jobs.values():
                if existing.topic == topic and existing.status in {"queued", "running", "waiting_input", "waiting_approval"}:
                    raise ValueError("このトピックでは、すでに Codex の処理が進行中です。")
            job = Job(uuid.uuid4().hex, action, topic, payload, phase=_phase_for(action))
            self._jobs[job.id] = job
            self._record(job, "status")
            self._queue.put(job.id)
            return job

    def get_job(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return job

    def reserve_lesson_resolution(self, job_id: str) -> Job:
        """Reserve one retry/continue choice until its new job is enqueued."""
        with self._lock:
            job = self.get_job(job_id)
            if getattr(job, "resolution_reserved", False) or getattr(job, "resolution_consumed", False):
                raise ValueError("この採点結果の次の操作はすでに開始されています。")
            if job.status != "completed" or job.action != "lesson_grade" or not isinstance(job.result, dict) or job.result.get("nextAction") != "retry_or_continue":
                raise ValueError("この採点結果から次の操作は開始できません。")
            job.resolution_reserved = True
            return job

    def release_lesson_resolution(self, job_id: str) -> None:
        """Undo an uncommitted reservation after create_job rejects it."""
        with self._lock:
            job = self.get_job(job_id)
            if not job.resolution_consumed:
                job.resolution_reserved = False

    def commit_lesson_resolution(self, job_id: str) -> None:
        """Make a reservation permanently single-use after queue insertion."""
        with self._lock:
            job = self.get_job(job_id)
            if not job.resolution_reserved or job.resolution_consumed:
                raise ValueError("この採点結果の次の操作はすでに開始されています。")
            job.resolution_reserved = False
            job.resolution_consumed = True

    def events_after(self, job_id: str, after: int) -> list[JobEvent]:
        with self._lock:
            return [event for event in self.get_job(job_id).events if event.id > after]

    def respond(self, job_id: str, response: dict[str, Any]) -> Job:
        with self._lock:
            job = self.get_job(job_id)
            if (
                self._client is None
                or self._active_id != job.id
                or job.status not in {"waiting_input", "waiting_approval"}
                or job.pending_request_id is None
                or job.pending_kind is None
            ):
                raise ValueError("現在、応答を待っていません。")
            request_id, kind = job.pending_request_id, job.pending_kind
            if kind == "input":
                if set(response) != {"answers"}:
                    raise ValueError("回答が不正です。")
                result = self._input_response(job, response)
            elif kind in {"command", "file"}:
                if set(response) != {"decision"}:
                    raise ValueError("承認の選択が不正です。")
                decision = response.get("decision")
                decisions = (job.pending_details or {}).get("decisions")
                if not isinstance(decisions, list) or decision not in decisions:
                    raise ValueError("承認の選択が不正です。")
                if decision == "cancel":
                    self._client.respond_to_server_request(request_id, {"decision": "cancel"})
                    return self.cancel(job_id)
                result = {"decision": decision}
            elif kind == "permissions":
                if set(response) != {"decision"}:
                    raise ValueError("承認の選択が不正です。")
                decision = response.get("decision")
                decisions = (job.pending_details or {}).get("decisions")
                if not isinstance(decisions, list) or decision not in decisions:
                    raise ValueError("承認の選択が不正です。")
                if decision == "cancel":
                    return self.cancel(job_id)
                result = self._permission_response(job, accept=decision == "accept")
            else:
                raise ValueError("Codex CLI 0.144.3 互換性エラー: 未対応の待機状態です。")
            self._clear_pending_request(job)
            job.status = "running"
            job.phase = _phase_for(job.action)
            job.message = "更新中です。"
            self._record(job, "status")
            self._client.respond_to_server_request(request_id, result)
            return job

    def cancel(self, job_id: str) -> Job:
        with self._lock:
            job = self.get_job(job_id)
            if job.status in {"completed", "failed", "cancelled"}:
                return job
            # A queued job has no App Server turn and can stop immediately.
            # A started turn must retain the topic lock until its terminal
            # notification arrives; an interrupt acknowledgement alone does
            # not prove that Codex has stopped writing Markdown.
            if job.status == "queued" and not job.thread_id and not job.turn_id:
                job.status = "cancelled"
                job.message = "処理を中止しました。"
                job.done.set()
                self._record(job, "status")
                return job
            if self._active_id != job.id:
                raise ValueError("このジョブは現在実行中ではありません。")
            job.cancel_requested = True
            job.status = "running"
            job.message = "停止中です。"
            self._clear_pending_request(job)
            self._record(job, "status")
            if self._client is not None and job.thread_id and job.turn_id:
                self._interrupt_turn_async(job, self._client_generation, self._client, job.thread_id, job.turn_id)
                self._arm_cancel_timeout(job)
            return job

    def _arm_cancel_timeout(self, job: Job) -> None:
        if job.cancel_timer is not None:
            return
        def expire() -> None:
            with self._lock:
                job.cancel_timer = None
                if (
                    (not job.cancel_requested and not job.failure_pending)
                    or job.status in {"completed", "failed", "cancelled"}
                ):
                    return
                # An interrupt acknowledgement does not establish that Codex
                # stopped writing. Only release the topic lock after the
                # transport synchronously proves its process is gone.
                if self._terminate_client_for_cancel():
                    if job.cancel_requested:
                        self._finish_cancel(job)
                    else:
                        self._finish_failed(job)
                    return
                # Keep the worker and topic lock live. Marking this job as a
                # terminal failure would let another job enter the same topic
                # while an unconfirmed process might still mutate Markdown.
                job.error = "Codex の停止を確認できないため、この学習セッションを保護しています。"
                job.message = "Codex の停止確認に失敗しました。学習セッションは保護中です。"
                self._record(job, "status")
                self._arm_cancel_timeout(job)
        job.cancel_timer = threading.Timer(self._cancel_timeout_seconds, expire)
        job.cancel_timer.daemon = True
        job.cancel_timer.start()

    def _terminate_client_for_cancel(self) -> bool:
        """Force-stop the App Server and return true only after proof of exit."""
        client = self._client
        if client is None:
            return False
        terminate = getattr(client, "terminate_for_cancel", None)
        if not callable(terminate):
            return False
        try:
            stopped = terminate()
        except Exception:
            return False
        if stopped is True:
            self._client = None
            return True
        return False

    def _finish_cancel(self, job: Job) -> None:
        if job.cancel_timer is not None:
            job.cancel_timer.cancel()
            job.cancel_timer = None
        job.status = "cancelled"
        job.message = "処理を中止しました。"
        self._clear_pending_request(job)
        job.done.set()
        self._record(job, "status")

    def _begin_failed_stop(self, job: Job, error: str) -> None:
        """Interrupt an unsafe turn but retain its topic lock until it stops."""
        job.failure_pending = True
        job.error = error
        job.message = "安全のため Codex の停止を確認しています。"
        self._clear_pending_request(job)
        self._record(job, "status")
        if self._client is not None and job.thread_id and job.turn_id:
            self._interrupt_turn_async(job, self._client_generation, self._client, job.thread_id, job.turn_id)
            self._arm_cancel_timeout(job)
        elif self._client is None:
            self._finish_failed(job)

    def _finish_failed(self, job: Job) -> None:
        if job.cancel_timer is not None:
            job.cancel_timer.cancel()
            job.cancel_timer = None
        job.failure_pending = False
        job.status = "failed"
        job.message = "処理を完了できませんでした。"
        self._clear_pending_request(job)
        job.done.set()
        self._record(job, "status")

    @staticmethod
    def _clear_pending_request(job: Job) -> None:
        job.pending_request_id = None
        job.pending_kind = None
        job.pending_details = None

    @staticmethod
    def _interrupt_turn_async(
        job: Job,
        generation: int,
        client: CodexAppServerClient,
        thread_id: str,
        turn_id: str,
    ) -> None:
        """Do not block an App Server reader callback on its own response."""
        key = (generation, thread_id, turn_id)
        if job.interrupt_key == key:
            return
        job.interrupt_key = key
        def interrupt() -> None:
            try:
                client.interrupt(thread_id=thread_id, turn_id=turn_id)
            except Exception:
                pass
        threading.Thread(target=interrupt, name="study-loop-codex-interrupt", daemon=True).start()

    def close(self) -> None:
        self._closed = True
        self._queue.put(None)
        if self._client is not None:
            self._client.close()

    def _record(self, job: Job, kind: str) -> None:
        job.events.append(JobEvent(job.next_event_id, kind, job.public()))
        job.next_event_id += 1
        if len(job.events) > 256:
            job.events.pop(0)

    def _work(self) -> None:
        while not self._closed:
            job_id = self._queue.get()
            if job_id is None:
                return
            job = self._jobs.get(job_id)
            if job is None or job.status == "cancelled":
                continue
            # Keep the lock through user questions and approvals as well as the
            # turn, so a browser submit cannot overwrite a Codex mutation.
            with self._topic_lock(job.topic):
                self._run_job(job)

    def _run_job(self, job: Job) -> None:
        with self._lock:
            if job.status == "cancelled":
                return
            job.status = "running"
            job.phase = _phase_for(job.action)
            job.message = "準備中です。"
            self._active_id = job.id
            self._record(job, "status")
        try:
            if self._client is None or self._client.crashed:
                self._client = self._client_factory()
                self._client_generation += 1
            client = self._client
            generation = self._client_generation
            client.set_handlers(
                on_notification=lambda message: self._on_notification(
                    message, source_client=client, source_generation=generation,
                ),
                on_request=lambda message: self._on_request(
                    message, source_client=client, source_generation=generation,
                ),
            )
            self.last_connection_status = client.connect(project_root=self.project_root)
            if not self.last_connection_status.authenticated or not self.last_connection_status.study_loop_skill_available:
                raise AppServerError(self.last_connection_status.message)
            with self._lock:
                if job.status == "cancelled":
                    return
                if job.cancel_requested and not job.thread_id and not job.turn_id:
                    self._finish_cancel(job)
                    return
                job.message = "準備中です。"
                self._record(job, "status")
            if self._preflight is not None:
                self._preflight(job.action, job.topic, job.payload)
            if self._snapshot_workflow is not None:
                job.workflow_snapshot = self._snapshot_workflow(job.topic)
            self._assert_confirmed_answer(job)
            job.thread_id, job.turn_id = client.start_turn(prompt=self._prompt_for(job), project_root=self.project_root)
            # The App Server resolves the transient launcher while composing
            # this exact turn's fixed PATH.  Do not use a launcher observed at
            # Flask start-up for a later turn.
            if hasattr(client, "apply_patch_launcher"):
                launcher = getattr(client, "apply_patch_launcher")
                self._apply_patch_launcher = launcher if isinstance(launcher, Path) else None
            with self._lock:
                early = job.early_notifications
                job.early_notifications = []
                early_requests = job.early_requests
                job.early_requests = []
                for notification in early:
                    self._on_notification(notification)
                for server_request in early_requests:
                    self._on_request(server_request)
                if job.cancel_requested and self._client is not None:
                    self._interrupt_turn_async(job, generation, client, job.thread_id, job.turn_id)
                    self._arm_cancel_timeout(job)
                if job.status == "running":
                    job.message = "採点中です。" if job.phase == "grading" else "更新中です。"
                    self._record(job, "status")
            while not job.done.wait(0.1):
                if self._client.crashed:
                    raise AppServerError("Codex App Server が予期せず終了しました。もう一度開始してください。")
        except (AppServerError, ValueError) as exc:
            with self._lock:
                if job.status != "cancelled":
                    if job.cancel_requested:
                        self._finish_cancel(job)
                    else:
                        job.error = _short(str(exc)) or "Codex を完了できませんでした。"
                        self._finish_failed(job)
        finally:
            with self._lock:
                self._active_id = None

    def _assert_confirmed_answer(self, job: Job) -> None:
        """Reject a browser edit made after confirmation but before the turn."""
        confirmed = job.payload.get("_confirmedAnswer")
        if confirmed is None:
            return
        if not isinstance(confirmed, dict):
            raise AppServerError("確認済みの回答情報が不正です。")
        kind = confirmed.get("kind")
        name = confirmed.get("name")
        revision = confirmed.get("revision")
        target = job.payload.get("target")
        if (
            kind not in {"diagnostic", "lessons"}
            or not isinstance(name, str)
            or not isinstance(revision, str)
            or not isinstance(target, dict)
            or target.get("kind") != kind
            or target.get("name") != name
        ):
            raise AppServerError("確認済みの回答情報が不正です。")
        topic_root = (self.project_root / ".study" / job.topic).resolve()
        expected_parent = topic_root / kind
        candidate = expected_parent / name
        try:
            resolved = candidate.resolve(strict=True)
            parent = expected_parent.resolve(strict=True)
        except OSError as exc:
            raise AppServerError("確認済みの回答が見つかりません。保存し直してください。") from exc
        if candidate.is_symlink() or not candidate.is_file() or parent not in resolved.parents:
            raise AppServerError("確認済みの回答が学習セッション外です。保存し直してください。")
        if hashlib.sha256(candidate.read_bytes()).hexdigest() != revision:
            raise AppServerError("回答が確認後に変更されました。保存し直してから採点してください。")

    def _active_job_for(self, params: dict[str, Any], method: str | None = None) -> Job | None:
        if self._active_id is None:
            return None
        job = self._jobs.get(self._active_id)
        if job is None or job.thread_id is None or job.turn_id is None:
            return None
        turn_id = params.get("turnId")
        if method == "turn/completed" and isinstance(params.get("turn"), dict):
            turn_id = params["turn"].get("id")
        if params.get("threadId") != job.thread_id or turn_id != job.turn_id:
            return None
        return job

    def _on_notification(
        self,
        message: dict[str, Any],
        *,
        source_client: CodexAppServerClient | None = None,
        source_generation: int | None = None,
    ) -> None:
        with self._lock:
            if source_client is not None and (
                source_client is not self._client or source_generation != self._client_generation
            ):
                return
            method = message.get("method")
            params = message.get("params") if isinstance(message.get("params"), dict) else {}
            if self._active_id is not None:
                starting = self._jobs.get(self._active_id)
                if starting is not None and starting.thread_id is None and starting.turn_id is None:
                    # The protocol may emit a turn event immediately after the
                    # turn/start response. Buffer only during this tiny window;
                    # it is still matched to IDs after start_turn returns.
                    starting.early_notifications.append(message)
                    return
            job = self._active_job_for(params, str(method))
            if job is None or job.status in {"cancelled", "completed", "failed"}:
                return
            if method == "item/started":
                item = params.get("item")
                item_type = item.get("type") if isinstance(item, dict) else None
                if item_type in {"mcpToolCall", "collabToolCall", "collabAgentToolCall"}:
                    # Config overrides are the primary control. Treat an
                    # unexpected integration item as a fail-closed backstop.
                    self._begin_failed_stop(
                        job,
                        "Codex が許可されていない外部連携または子エージェントを開始しました。",
                    )
                return
            if method == "item/agentMessage/delta":
                delta = params.get("delta")
                if isinstance(delta, str):
                    job.agent_text += delta
                    item_id = params.get("itemId")
                    if isinstance(item_id, str):
                        job.agent_text_by_item[item_id] = job.agent_text_by_item.get(item_id, "") + delta
                return
            if method == "item/completed":
                item = params.get("item")
                if not isinstance(item, dict) or item.get("type") != "agentMessage":
                    return
                phase = item.get("phase")
                if phase == "commentary":
                    return
                candidate = _completed_agent_result(item)
                if candidate is not None:
                    job.final_agent_item_id, job.final_agent_text = candidate
                elif phase == "final_answer" and isinstance(item.get("id"), str):
                    # A malformed explicit final answer may still fall back
                    # to its own deltas, but never to another item's stream.
                    job.final_agent_item_id = item["id"]
                return
            if method != "turn/completed":
                return
            turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
            if job.failure_pending:
                if turn.get("id") == job.turn_id and turn.get("status") in {"completed", "cancelled", "interrupted", "failed"}:
                    self._finish_failed(job)
                return
            if job.cancel_requested:
                if turn.get("id") == job.turn_id and turn.get("status") in {"completed", "cancelled", "interrupted", "failed"}:
                    self._finish_cancel(job)
                return
            if turn.get("id") != job.turn_id or turn.get("status") != "completed":
                job.status = "failed"
                job.error = "Codex の処理が完了しませんでした。"
            else:
                try:
                    if job.final_agent_text is None:
                        embedded = _final_result_from_turn_items(turn.get("items"))
                        if embedded is not None:
                            job.final_agent_item_id, job.final_agent_text = embedded
                    if job.final_agent_text is not None:
                        result_text = job.final_agent_text
                    elif job.final_agent_item_id is not None:
                        result_text = job.agent_text_by_item.get(job.final_agent_item_id, "")
                    else:
                        result_text = job.agent_text
                    job.result = _validate_result(json.loads(result_text), self.project_root, job.topic, job.action)
                    if self._postflight is not None:
                        self._postflight(job.action, job.topic, job.payload, job.result, job.workflow_snapshot)
                    job.status = "completed"
                    job.message = "完了しました。"
                except (json.JSONDecodeError, ValueError):
                    job.status = "failed"
                    job.error = "Codex の最終結果を確認できませんでした。"
                    job.message = "処理を完了できませんでした。"
            self._clear_pending_request(job)
            job.done.set()
            self._record(job, "status")

    def _on_request(
        self,
        message: dict[str, Any],
        *,
        source_client: CodexAppServerClient | None = None,
        source_generation: int | None = None,
    ) -> None:
        with self._lock:
            if source_client is not None and (
                source_client is not self._client or source_generation != self._client_generation
            ):
                return
            if self._client is None:
                return
            method = message.get("method")
            request_id = message.get("id")
            params = message.get("params") if isinstance(message.get("params"), dict) else {}
            if not isinstance(request_id, (str, int)):
                return
            if self._active_id is not None:
                starting = self._jobs.get(self._active_id)
                if starting is not None and starting.thread_id is None and starting.turn_id is None:
                    # A request can race the turn/start response. Preserve the
                    # complete JSON-RPC request and correlate it only after the
                    # returned IDs have been attached to this job.
                    starting.early_requests.append(message)
                    return
            job = self._active_job_for(params, str(method))
            if job is None:
                return  # Late event from a previous thread/turn.
            if method not in REQUEST_METHODS:
                self._client.respond_to_server_error(request_id, -32601, "Codex CLI 0.144.3 compatibility failure")
                self._begin_failed_stop(job, f"Codex CLI 0.144.3 互換性エラー: 未対応の要求 {method}。")
                return
            try:
                if method == "item/tool/requestUserInput":
                    details = self._input_details(params)
                    kind = "input"
                elif method == "item/commandExecution/requestApproval":
                    details = self._approval_details("command", params)
                    kind = "command"
                elif method == "item/fileChange/requestApproval":
                    details = self._approval_details("file", params)
                    kind = "file"
                else:
                    details = self._approval_details("permissions", params)
                    setattr(job, "_permission_request", params)
                    kind = "permissions"
            except ValueError as exc:
                self._client.respond_to_server_error(request_id, -32602, "Codex CLI 0.144.3 compatibility failure")
                self._begin_failed_stop(job, _short(str(exc)))
                return
            if (
                self._has_external_request(params, topic=job.topic)
                or self._has_inline_code_request(params, topic=job.topic)
                or not self._approval_is_provable(kind, params, details, topic=job.topic)
            ):
                self._auto_deny(job, request_id, kind)
                return
            job.status = "waiting_input" if kind == "input" else "waiting_approval"
            job.phase = "confirming"
            job.pending_request_id = request_id
            job.pending_kind = kind
            job.pending_details = details
            job.message = "確認中です。"
            self._record(job, "status")

    def _auto_deny(self, job: Job, request_id: RequestId, kind: str) -> None:
        assert self._client is not None
        if kind == "permissions":
            self._client.respond_to_server_request(request_id, {"permissions": {}, "scope": "turn"})
        else:
            self._client.respond_to_server_request(request_id, {"decision": "decline"})
        job.message = "安全を確認できない操作要求を拒否しました。"
        self._record(job, "status")

    def _input_details(self, params: dict[str, Any]) -> dict[str, Any]:
        questions: list[dict[str, Any]] = []
        raw_questions = params.get("questions")
        if not isinstance(raw_questions, list) or not 1 <= len(raw_questions) <= 3:
            raise ValueError("Codex CLI 0.144.3 互換性エラー: 質問数が不正です。")
        for question in raw_questions:
            if not isinstance(question, dict) or not all(isinstance(question.get(key), str) for key in ("id", "header", "question")):
                raise ValueError("Codex CLI 0.144.3 互換性エラー: 質問形式が不正です。")
            options = question.get("options")
            clean_options: list[dict[str, str]] = []
            if isinstance(options, list):
                for option in options[:8]:
                    if isinstance(option, dict) and isinstance(option.get("label"), str) and isinstance(option.get("description"), str):
                        clean_options.append({"label": _short(option["label"]), "description": _short(option["description"])})
            questions.append({
                "id": question["id"], "header": _short(question["header"]), "question": _short(question["question"]),
                "options": clean_options, "isOther": bool(question.get("isOther")), "isSecret": bool(question.get("isSecret")),
            })
        return {"questions": questions}

    def _approval_details(self, kind: str, params: dict[str, Any]) -> dict[str, Any]:
        network = params.get("networkApprovalContext")
        if network is not None and (not isinstance(network, dict) or not isinstance(network.get("host"), str)):
            raise ValueError("Codex CLI 0.144.3 互換性エラー: 通信承認の形式が不正です。")
        network_host = network.get("host") if isinstance(network, dict) else None
        paths = self._requested_paths(params)
        decisions = self._available_decisions(kind, params)
        additional = params.get("additionalPermissions") if kind == "command" else params.get("permissions") if kind == "permissions" else None
        return {
            "kind": kind, "command": _request_text(params.get("command"), limit=APPLY_PATCH_MAX_BYTES * 2), "reason": _request_text(params.get("reason"), limit=4_000),
            "cwd": _request_text(params.get("cwd"), limit=4_000), "networkHost": _request_text(network_host, limit=1_000) if network_host else None,
            "paths": paths, "permissions": self._approval_permissions_text(additional), "decisions": decisions,
        }

    def _available_decisions(self, kind: str, params: dict[str, Any]) -> list[str]:
        if kind != "command":
            return ["accept", "decline", "cancel"]
        available = params.get("availableDecisions")
        if available is None:
            # A missing list supplies no server-advertised response value.
            return []
        if not isinstance(available, list):
            raise ValueError("Codex CLI 0.144.3 互換性エラー: 承認候補が不正です。")
        # Structured options can describe persistent approvals. This UI never
        # invents or sends them; retain only exact, one-turn string choices.
        return [item for item in available if isinstance(item, str) and item in {"accept", "decline", "cancel"}]

    def _approval_permissions_text(self, profile: Any) -> str:
        if profile is None:
            return ""
        try:
            text = json.dumps(profile, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Codex CLI 0.144.3 互換性エラー: 権限内容が不正です。") from exc
        return _request_text(text)

    def _approval_is_provable(self, kind: str, params: dict[str, Any], details: dict[str, Any], *, topic: str) -> bool:
        if kind == "command":
            additional = params.get("additionalPermissions")
            if additional is not None and not self._safe_additional_permissions(additional):
                return False
            cwd = self._request_cwd(params)
            return (
                cwd is not None
                and self._command_is_approval_safe(params.get("command"), cwd, topic)
                and self._command_actions_are_approval_safe(params.get("commandActions"), cwd, params.get("command"), topic)
                and bool(details.get("decisions"))
            )
        if kind == "file":
            grant_root = params.get("grantRoot")
            return grant_root is None or (isinstance(grant_root, str) and self._inside_project(grant_root))
        if kind == "permissions":
            profile = params.get("permissions")
            return isinstance(profile, dict) and bool(self._safe_permission_subset(profile) or not profile)
        return True

    def _safe_additional_permissions(self, profile: Any) -> bool:
        if not isinstance(profile, dict) or set(profile) - {"fileSystem", "network"}:
            return False
        file_system = profile.get("fileSystem")
        if file_system is not None:
            if not isinstance(file_system, dict) or set(file_system) - {"read", "write", "entries", "globScanMaxDepth"}:
                return False
            for key in ("read", "write"):
                values = file_system.get(key)
                if values is not None and (not isinstance(values, list) or any(not isinstance(path, str) or not self._inside_project(path) for path in values)):
                    return False
            entries = file_system.get("entries")
            if entries is not None and (not isinstance(entries, list) or any(not isinstance(entry, dict) or not self._entry_inside_project(entry) for entry in entries)):
                return False
        network = profile.get("network")
        return network is None or (isinstance(network, dict) and set(network) <= {"enabled"} and isinstance(network.get("enabled"), bool))

    def _input_response(self, job: Job, response: dict[str, Any]) -> dict[str, Any]:
        answers = response.get("answers")
        questions = (job.pending_details or {}).get("questions")
        if not isinstance(answers, dict) or not isinstance(questions, list):
            raise ValueError("回答が不正です。")
        result: dict[str, Any] = {}
        for question in questions:
            question_id = question.get("id")
            values = answers.get(question_id)
            if not isinstance(question_id, str) or not isinstance(values, list) or not 1 <= len(values) <= 8:
                raise ValueError("すべての質問に回答してください。")
            if any(not isinstance(value, str) or len(value) > 4000 for value in values):
                raise ValueError("回答が不正です。")
            result[question_id] = {"answers": values}
        return {"answers": result}

    def _permission_response(self, job: Job, *, accept: bool) -> dict[str, Any]:
        if not accept:
            return {"permissions": {}, "scope": "turn"}
        # Raw request data is deliberately not public. It is saved privately on
        # the Job just before this function is called by _on_request.
        raw = getattr(job, "_permission_request", {})
        profile = raw.get("permissions") if isinstance(raw, dict) else {}
        granted = self._safe_permission_subset(profile if isinstance(profile, dict) else {})
        return {"permissions": granted, "scope": "turn"}

    def _safe_permission_subset(self, profile: dict[str, Any]) -> dict[str, Any]:
        file_system = profile.get("fileSystem")
        network = profile.get("network")
        granted: dict[str, Any] = {}
        if isinstance(file_system, dict):
            safe: dict[str, Any] = {}
            for key in ("read", "write"):
                values = file_system.get(key)
                if isinstance(values, list):
                    safe_values = [path for path in values if isinstance(path, str) and self._inside_project(path)]
                    if safe_values:
                        safe[key] = safe_values
            entries = file_system.get("entries")
            if isinstance(entries, list):
                safe_entries = [entry for entry in entries if isinstance(entry, dict) and self._entry_inside_project(entry)]
                if safe_entries:
                    safe["entries"] = safe_entries
            if safe:
                granted["fileSystem"] = safe
        if isinstance(network, dict) and network.get("enabled") is True:
            granted["network"] = {"enabled": True}
        return granted

    def _has_external_request(self, params: dict[str, Any], *, topic: str | None = None) -> bool:
        cwd = self._request_cwd(params)
        if cwd is None:
            return True
        grant_root = params.get("grantRoot")
        if isinstance(grant_root, str) and not self._inside_project(grant_root, base=cwd):
            return True
        for path in self._requested_paths_raw(params, include_command_actions=False):
            if not self._inside_project(path, base=cwd):
                return True
        command = params.get("command")
        if command is None:
            return False
        if topic is not None and self._apply_patch_command_argv(command, topic) is not None:
            return False
        return (
            not self._command_paths_are_local(command, cwd)
            or not self._command_actions_are_approval_safe(params.get("commandActions"), cwd, command, topic)
        )

    def _has_inline_code_request(self, params: dict[str, Any], *, topic: str | None = None) -> bool:
        """Reject command lines that carry executable source as an argument."""
        if topic is not None and self._apply_patch_command_argv(params.get("command"), topic) is not None:
            return False
        commands: list[Any] = [params.get("command")]
        actions = params.get("commandActions")
        if isinstance(actions, list):
            commands.extend(action.get("command") for action in actions if isinstance(action, dict))
        return any(self._command_has_inline_code(command) for command in commands)

    def _command_has_inline_code(self, command: Any) -> bool:
        if not isinstance(command, str) or not command:
            return False
        if self._command_has_unprovable_shell_syntax(command):
            return True
        if self._is_system_shell_wrapper(command):
            inner_argv = self._safe_system_shell_inner_argv(command)
            # A known shell's ``-c`` argument is executable source unless it
            # satisfies the deliberately narrow single-command grammar below.
            return inner_argv is None or self._argv_has_inline_code(inner_argv)
        try:
            return self._argv_has_inline_code(shlex.split(command, posix=True))
        except ValueError:
            return True

    @staticmethod
    def _command_has_unprovable_shell_syntax(command: str) -> bool:
        """Reject syntax whose executed argv cannot be proven without a shell.

        ``shlex`` is only an argv lexer; it does not expand POSIX shell syntax.
        Browser approval is therefore limited to simple commands. Redirection
        is deliberately excluded even when its target appears project-local:
        the shell performs it before the executable is checked.
        """
        if re.search(r"[\\\\$`~*?\[\]{}();|&<>\n]", command):
            return True
        # Process substitutions are executable even though they can look like
        # an ordinary redirection to a token-based parser.
        if re.search(r"[<>]\(", command) or "<<" in command:
            return True
        return False

    def _command_is_approval_safe(self, command: Any, cwd: Path, topic: str) -> bool:
        """Allow bounded reads plus Codex's verified apply_patch launcher."""
        if not isinstance(command, str):
            return False
        if self._apply_patch_command_argv(command, topic) is not None:
            return self._apply_patch_launcher is not None
        argv = self._approval_command_argv(command)
        if argv is None:
            return False
        return self._argv_is_approval_safe(argv, cwd)

    def _command_actions_are_approval_safe(self, actions: Any, cwd: Path, command: Any, topic: str | None = None) -> bool:
        """Accept only verified 0.144.3 annotations for this exact read argv."""
        apply_patch_argv = self._apply_patch_command_argv(command, topic) if topic is not None else None
        if apply_patch_argv is not None:
            return (
                self._apply_patch_launcher is not None
                and isinstance(actions, list)
                and len(actions) == 1
                and isinstance(actions[0], dict)
                and set(actions[0]) == {"type", "command"}
                and actions[0].get("type") == "unknown"
                and self._apply_patch_inner_argv(actions[0].get("command"), topic) == apply_patch_argv
            )
        if actions is None:
            return True
        outer_argv = self._approval_command_argv(command)
        if outer_argv is None or not self._argv_is_approval_safe(outer_argv, cwd) or not isinstance(actions, list) or not actions:
            return False
        normalized_outer = self._normalized_approval_argv(outer_argv)
        if normalized_outer is None:
            return False
        for action in actions:
            if not isinstance(action, dict):
                return False
            action_command = action.get("command")
            action_argv = self._approval_command_argv(action_command, allow_shell_wrapper=False)
            if action_argv is None or self._normalized_approval_argv(action_argv) != normalized_outer:
                return False
            if action.get("type") == "unknown":
                # App Server 0.144.3 labels this fixed digest invocation as
                # unknown. Accept no other unknown annotation or metadata.
                if set(action) != {"type", "command"} or not self._argv_is_sha256_integrity_check(outer_argv, cwd):
                    return False
                continue
            if action.get("type") not in {"read", "listFiles"}:
                return False
            path = action.get("path")
            if path is not None and not isinstance(path, str):
                return False
            if action["type"] == "read":
                if not isinstance(action.get("name"), str) or not isinstance(path, str) or not self._read_path_is_approval_safe(path, cwd):
                    return False
            elif path is not None and not self._inside_project(path, base=cwd):
                return False
        return True

    def _apply_patch_command_argv(self, command: Any, topic: str) -> list[str] | None:
        """Parse only the exact App Server ``zsh -c`` apply-patch wrapper.

        The patch is an argument, never shell source.  Reconstructing the
        inner argv with ``shlex.join`` proves that no expansion, chaining, or
        extra outer argument was hidden in the request.
        """
        if not isinstance(command, str) or not command:
            return None
        try:
            outer = shlex.split(command, posix=True)
        except ValueError:
            return None
        if len(outer) != 3 or outer[:2] != ["/bin/zsh", "-c"]:
            return None
        return self._apply_patch_inner_argv(outer[2], topic)

    def _apply_patch_inner_argv(self, command: Any, topic: str) -> list[str] | None:
        """Return a proved literal ``apply_patch`` argv for one active topic."""
        if not isinstance(command, str) or not command:
            return None
        try:
            argv = shlex.split(command, posix=True)
        except ValueError:
            return None
        if len(argv) not in {1, 2} or argv[0] != "apply_patch" or shlex.join(argv) != command:
            return None
        if len(argv) == 2 and not self._apply_patch_text_is_safe(argv[1], topic):
            return None
        return argv

    def _apply_patch_text_is_safe(self, patch: str, topic: str) -> bool:
        """Allow a bounded Add/Update-only Markdown patch in one session."""
        if "\x00" in patch or "\r" in patch or len(patch.encode("utf-8")) > APPLY_PATCH_MAX_BYTES:
            return False
        lines = patch.splitlines()
        if len(lines) < 3 or lines[0] != "*** Begin Patch" or lines[-1] != "*** End Patch":
            return False
        targets = 0
        for line in lines[1:-1]:
            if not line.startswith("*** "):
                continue
            match = re.fullmatch(r"\*\*\* (Add|Update) File: (.+)", line)
            if match is None or not self._apply_patch_target_is_safe(match.group(1), match.group(2), topic):
                return False
            targets += 1
        return targets > 0

    def _apply_patch_target_is_safe(self, operation: str, value: str, topic: str) -> bool:
        """Prove one patch target stays in existing active-topic Markdown."""
        if not value or value != value.strip() or "\x00" in value or "\\" in value:
            return False
        parts = tuple(value.split("/"))
        if (
            len(parts) < 4
            or any(part in {"", ".", ".."} for part in parts)
            or parts[:2] != (".study", topic)
            or not value.endswith(".md")
        ):
            return False
        target = self.project_root.joinpath(*parts)
        topic_root = self.project_root / ".study" / topic
        if _contains_symlink_component(self.project_root, parts):
            return False
        try:
            resolved_topic = topic_root.resolve(strict=True)
            resolved_parent = target.parent.resolve(strict=True)
        except OSError:
            return False
        if not resolved_parent.is_dir() or (resolved_parent != resolved_topic and resolved_topic not in resolved_parent.parents):
            return False
        if operation == "Update":
            try:
                resolved_target = target.resolve(strict=True)
            except OSError:
                return False
            return target.is_file() and not target.is_symlink() and resolved_target.suffix == ".md" and (
                resolved_target != resolved_topic and resolved_topic in resolved_target.parents
            )
        return operation == "Add" and not target.exists() and not target.is_symlink()

    def _argv_is_approval_safe(self, argv: list[str], cwd: Path) -> bool:
        argv = self._normalized_approval_argv(argv) or []
        if not argv:
            return False
        executable = argv[0]
        args = argv[1:]
        if executable == "pwd":
            return len(argv) == 1
        if executable == "ls":
            return self._ls_args_are_approval_safe(args, cwd)
        if executable == "git":
            return len(args) == 4 and args[:3] == ["status", "--short", "--"] and self._inside_project(args[3], base=cwd)
        if executable == "rg":
            return self._rg_files_args_are_approval_safe(args, cwd)
        if executable == "sed":
            return len(args) == 3 and args[0] == "-n" and bool(re.fullmatch(r"\d+(?:,\d+)?p", args[1])) and self._read_path_is_approval_safe(args[2], cwd)
        if executable == "cat":
            return len(args) == 1 and self._read_path_is_approval_safe(args[0], cwd)
        if executable == "shasum":
            return self._argv_is_sha256_integrity_check(argv, cwd)
        return False

    def _argv_is_sha256_integrity_check(self, argv: list[str], cwd: Path) -> bool:
        """Allow exactly one SHA-256 check of an existing regular local file."""
        normalized = self._normalized_approval_argv(argv)
        if normalized is None or len(normalized) != 4 or normalized[:3] != ["shasum", "-a", "256"]:
            return False
        candidate = Path(normalized[3])
        if not candidate.is_absolute():
            candidate = cwd / candidate
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            return False
        return resolved.is_file() and (resolved == self.project_root or self.project_root in resolved.parents)

    def _ls_args_are_approval_safe(self, args: list[str], cwd: Path) -> bool:
        """Accept display-only short flags and at most one project-local target."""
        index = 0
        while index < len(args) and args[index].startswith("-") and args[index] != "-":
            if not re.fullmatch(r"-[alh]+", args[index]):
                return False
            index += 1
        return len(args) - index <= 1 and (index == len(args) or self._inside_project(args[index], base=cwd))

    def _rg_files_args_are_approval_safe(self, args: list[str], cwd: Path) -> bool:
        """Accept only `rg --files` with one or more project-local roots."""
        return (
            len(args) >= 2
            and args[0] == "--files"
            and all(not path.startswith("-") and self._inside_project(path, base=cwd) for path in args[1:])
        )

    def _read_path_is_approval_safe(self, value: str, cwd: Path) -> bool:
        return self._inside_project(value, base=cwd) or self._is_bundled_skill_read_path(value, base=cwd)

    def _argv_has_inline_code(self, argv: list[str]) -> bool:
        """Recognize interpreter code switches after safe argv parsing only."""
        index = 0
        while index < len(argv) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", argv[index]):
            index += 1
        if index >= len(argv):
            return False

        executable = Path(argv[index]).name.lower()
        args = argv[index + 1:]
        if executable in {"env", "command", "exec", "nice", "time", "noglob", "eval", "source", ".", "xargs", "sudo", "doas", "nohup", "setsid"}:
            # These wrappers alter how the following command is dispatched.
            # Their option grammars vary by shell/platform, or they execute a
            # string indirectly, so do not try to prove a browser approval.
            return True
        if executable == "find" and any(arg in {"-exec", "-execdir", "-ok", "-okdir"} for arg in args):
            return True
        return self._interpreter_has_inline_code(executable, args)

    def _command_wrapped_inline_code(self, args: list[str]) -> bool:
        """Unwrap execution-preserving POSIX ``command`` options."""
        index = 0
        while index < len(args):
            token = args[index]
            if token == "--":
                index += 1
                break
            if token.startswith("-") and token != "-":
                # ``command -p`` only selects the standard command search
                # path, so it still dispatches the following command. ``-v``
                # and ``-V`` only query a name and must not be treated as an
                # executable wrapper.
                if set(token[1:]) <= {"p"}:
                    index += 1
                    continue
                return False
            break
        return self._argv_has_inline_code(args[index:]) if index < len(args) else False

    def _env_wrapped_inline_code(self, args: list[str]) -> bool:
        index = 0
        while index < len(args):
            token = args[index]
            if token == "--":
                index += 1
                break
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token):
                index += 1
                continue
            if token in {"-u", "--unset", "-C", "--chdir"}:
                index += 2
                continue
            if token in {"-S", "--split-string"}:
                # ``env -S`` reparses its following argument as a command
                # line.  It can hide interpreter switches across argv
                # boundaries, so it is never browser-approvable.
                return True
            if token.startswith(("--unset=", "--chdir=")) or token.startswith("-"):
                index += 1
                continue
            break
        return self._argv_has_inline_code(args[index:]) if index < len(args) else False

    @staticmethod
    def _interpreter_has_inline_code(executable: str, args: list[str]) -> bool:
        if executable in {"sh", "bash", "zsh", "dash"}:
            return any(arg == "-c" or (arg.startswith("-") and not arg.startswith("--") and "c" in arg[1:]) for arg in args)
        if executable == "fish":
            return any(arg in {"-c", "--command", "-C", "--init-command"} or arg.startswith(("--command=", "--init-command=")) for arg in args)
        if re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", executable):
            return any(arg == "-c" or arg.startswith("-c") or arg in {"--command"} or arg.startswith("--command=") for arg in args)
        if executable in {"node", "nodejs"}:
            return any(arg in {"-e", "-p", "--eval", "--print"} or arg.startswith(("-e", "-p", "--eval=", "--print=")) for arg in args)
        if executable == "ruby":
            return any(arg == "-e" or arg.startswith("-e") or arg == "--eval" or arg.startswith("--eval=") for arg in args)
        if executable == "perl":
            return any(arg in {"-e", "-E", "--eval"} or arg.startswith(("-e", "-E", "--eval=")) for arg in args)
        if executable == "php":
            return any(arg == "-r" or arg.startswith("-r") or arg == "--run" or arg.startswith("--run=") for arg in args)
        return False

    def _request_cwd(self, params: dict[str, Any]) -> Path | None:
        value = params.get("cwd")
        if value is None:
            return self.project_root
        if not isinstance(value, str):
            return None
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = self.project_root / candidate
        try:
            resolved = candidate.resolve(strict=False)
        except OSError:
            return None
        if resolved != self.project_root and self.project_root not in resolved.parents:
            return None
        return resolved

    @staticmethod
    def _is_system_shell_wrapper(command: str) -> bool:
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError:
            return False
        return bool(tokens) and tokens[0] in SYSTEM_SHELL_WRAPPERS

    @staticmethod
    def _safe_system_shell_inner_argv(command: str) -> list[str] | None:
        """Parse only a fixed system-shell wrapper around one simple command.

        Codex may use ``/bin/zsh -lc pwd`` solely to establish its working
        directory.  The shell source is still untrusted, so accept it only
        when it contains one argv-style command without shell syntax.
        """
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError:
            return None
        if len(tokens) != 3 or tokens[0] not in SYSTEM_SHELL_WRAPPERS or tokens[1] != "-c":
            return None

        source = tokens[2]
        # Do not evaluate a shell program in the browser approval path.  This
        # rejects expansion, chaining, redirects, globs, and escaped syntax.
        if re.search(r"[\\$`~*?\[\]{}();|&<>\n]", source):
            return None
        try:
            inner_argv = shlex.split(source, posix=True)
        except ValueError:
            return None
        return inner_argv or None

    def _approval_command_argv(self, command: Any, *, allow_shell_wrapper: bool = True) -> list[str] | None:
        if not isinstance(command, str) or not command:
            return None
        if self._is_system_shell_wrapper(command):
            if not allow_shell_wrapper:
                return None
            return self._safe_system_shell_inner_argv(command)
        if self._command_has_unprovable_shell_syntax(command):
            return None
        try:
            return shlex.split(command, posix=True)
        except ValueError:
            return None

    def _normalized_approval_argv(self, argv: list[str]) -> list[str] | None:
        """Canonicalize only fixed executable spellings, never a caller PATH."""
        if not argv:
            return None
        executable = argv[0]
        for name, canonical in self._approved_executables.items():
            if executable == name:
                return [name, *argv[1:]]
            if Path(executable).is_absolute():
                try:
                    if Path(executable).resolve(strict=True) == canonical:
                        return [name, *argv[1:]]
                except OSError:
                    return None
        return None

    def _command_paths_are_local(self, command: Any, cwd: Path) -> bool:
        """Conservatively prove that shell path arguments stay under ``cwd``."""
        if not isinstance(command, str) or not command:
            return False
        if self._is_system_shell_wrapper(command):
            inner_argv = self._safe_system_shell_inner_argv(command)
            return inner_argv is not None and self._tokens_paths_are_local(inner_argv, cwd)
        # Shell expansion makes the actual target unknowable without running
        # the command, so it is not eligible for browser approval.
        if re.search(r"\$\(|`|\$[A-Za-z_{]|[;|&\n]", command):
            return False
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError:
            return False
        if not tokens:
            return False

        return self._tokens_paths_are_local(tokens, cwd)

    def _tokens_paths_are_local(self, tokens: list[str], cwd: Path) -> bool:
        path_tokens: list[str] = []
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if index == 0:
                index += 1
                continue
            redirect = re.fullmatch(r"(?:\d+)?(?:>>?|<<?)(.*)", token)
            if token in {">", ">>", "<", "<<"} or (redirect and not redirect.group(1)):
                index += 1
                if index >= len(tokens):
                    return False
                path_tokens.append(tokens[index])
            elif redirect and redirect.group(1):
                path_tokens.append(redirect.group(1))
            else:
                # ``dd if=/tmp/x`` is an absolute filesystem operand even
                # though it does not begin with a slash. Treat every key=value
                # value as a possible path rather than only long options.
                option_value = token.split("=", 1)[1] if "=" in token else token
                if (
                    option_value in {".", ".."}
                    or option_value.startswith(("~", "/", "./", "../"))
                    or "/" in option_value
                    or option_value.endswith((".md", ".txt", ".json", ".py", ".sh"))
                ):
                    path_tokens.append(option_value)
            index += 1
        return all(self._read_path_is_approval_safe(path, cwd) for path in path_tokens)

    @staticmethod
    def _bundled_skill_root() -> Path:
        return Path(__file__).resolve().parent.parent

    def _is_bundled_skill_read_path(self, value: str, *, base: Path) -> bool:
        """Allow an existing regular file only when its canonical path stays in Study Loop."""
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = base / candidate
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            return False
        root = self._bundled_skill_root()
        return resolved.is_file() and root in resolved.parents

    def _inside_project(self, value: str, *, base: Path | None = None) -> bool:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = (base or self.project_root) / candidate
        try:
            resolved = candidate.resolve(strict=False)
        except OSError:
            return False
        return resolved == self.project_root or self.project_root in resolved.parents

    def _requested_paths_raw(self, params: Any, *, include_command_actions: bool = True) -> list[str]:
        found: list[str] = []
        def visit(value: Any, key: str = "") -> None:
            if isinstance(value, dict):
                for nested_key, nested in value.items():
                    if nested_key == "commandActions" and not include_command_actions:
                        continue
                    if nested_key in {"path", "grantRoot", "cwd", "pattern"} and isinstance(nested, str):
                        found.append(nested)
                    visit(nested, nested_key)
            elif isinstance(value, list):
                for nested in value:
                    # The generated App Server schema still accepts the legacy
                    # read/write lists. Treat every entry as a filesystem path
                    # before showing or granting the request.
                    if key in {"read", "write"} and isinstance(nested, str):
                        found.append(nested)
                    visit(nested, key)
        visit(params)
        return found

    def _requested_paths(self, params: dict[str, Any]) -> list[str]:
        return [_short(path) for path in self._requested_paths_raw(params)[:12]]

    def _entry_inside_project(self, entry: dict[str, Any]) -> bool:
        target = entry.get("path")
        return isinstance(target, dict) and target.get("type") == "path" and isinstance(target.get("path"), str) and self._inside_project(target["path"])

    def _prompt_for(self, job: Job) -> str:
        contract = """Study Loop の学習ワークフローを実行してください。必要な学習仕様、参照資料、既存 session assets を読み、Markdown を唯一の正として扱ってください。project root の .study 以外には書き込まないでください。ブラウザから任意の指示・パス・作業ディレクトリは渡されていません。Codex App Server のこの turn では、外部ツール、MCP、サブエージェント、ネストした Codex を呼び出さないでください。Generator、Critic、FB-Critic は同じ turn 内で順番に検討する論理的な役割であり、別の実行環境や子エージェントに委譲しません。回答の revision はサーバーが直前に SHA-256 を再検証済みなので、原則として再計算しないでください。コマンドが必要なら、1回の要求につき1つの承認済み読取コマンドだけを要求してください。&&、パイプ、リダイレクト、複合シェルは禁止です。ファイル一覧は rg --filesを対象ごとに別々に実行し、内容読取はcatまたはsed -nをファイルごとに別々に実行してください。Markdown の更新は Codex 標準の apply_patch ツールだけを使ってください。perl、sed -i、python、シェルリダイレクトなどによる書き込みは禁止です。apply_patch は1回の要求で project root 内の .study/<topic> にある必要なファイルだけを変更してください。承認後に cat で確認できます。最後は指定された JSON Schema にだけ一致する結果を返してください。"""
        action_lines = {
            "session_start": "学習条件から README.md、curriculum.md の枠、必要初期資産を作り、Generator-Critic を経た diagnostic/01-*.md を生成してください。不足だけ質問してください。",
            "diagnostic_grade": "固定された診断ファイルを採点・解説し、必要なら次の診断、4問目なら summary.md を生成してください。",
            "diagnostic_accept": "診断とユーザー調整を反映し、RESOURCES.md と curriculum.md を生成してください。",
            "curriculum_revise": "許可済みのフィードバックを反映して RESOURCES.md と curriculum.md を修正してください。",
            "curriculum_accept": "Generator-Critic を経て最初の lesson を生成してください。",
            "lesson_grade": "固定された lesson の採点プロトコルを実行し、関連 Markdown を更新し、必要なら次 lesson を生成してください。",
            "spaced_review": "同じ問題の再出題ではない別バリエーションの review lesson を生成してください。",
            "session_end": "README.md の Ended と Summary を更新し、次回の学習開始を要約してください。",
        }
        resolution = job.payload.get("resolution") if job.action == "lesson_grade" else None
        if resolution == "retry":
            action_line = "採点済み lesson を再採点しないでください。元の弱点を狙う、内容と表現が異なる新しい課題を生成してください。"
        elif resolution == "continue":
            action_line = "採点済み lesson を再採点しないでください。カリキュラムの次の未完了項目へ進む課題を生成してください。"
        else:
            action_line = action_lines[job.action]
        payload = json.dumps(job.payload, ensure_ascii=False, separators=(",", ":"))
        return f"{contract}\n\n操作: {job.action}\n対象セッション: .study/{job.topic}\n{action_line}\n\nサーバーで検証済みの学習データ: {payload}"
