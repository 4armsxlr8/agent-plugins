"""Portable schema checks for the local Codex App Server fake peers.

When the generated 0.144.3 schema bundle is present, these checks use the
specific response/notification schemas.  The small fallback validator keeps
the tests useful in a checkout that does not include the generated bundle.
The schema bundle location is configurable via the STUDY_LOOP_APP_SERVER_SCHEMA_ROOT
environment variable; when unset (the common case for a fresh checkout), the
bundle simply will not be found and every check falls back automatically.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


SCHEMA_ROOT = Path(os.environ.get("STUDY_LOOP_APP_SERVER_SCHEMA_ROOT", "app-server-schema"))


def _schema(path: str) -> dict[str, Any] | None:
    candidate = SCHEMA_ROOT / path
    if not candidate.is_file():
        return None
    return json.loads(candidate.read_text(encoding="utf-8"))


def _resolve(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    reference = schema.get("$ref")
    if not isinstance(reference, str) or not reference.startswith("#/definitions/"):
        return schema
    value: Any = root.get("definitions", {})
    for part in reference.removeprefix("#/definitions/").split("/"):
        value = value[part]
    return value


def _validate(value: Any, schema: dict[str, Any], root: dict[str, Any]) -> None:
    if schema is True:
        return
    if schema is False:
        raise AssertionError("schema rejects every value")
    schema = _resolve(schema, root)
    for key in ("allOf",):
        for child in schema.get(key, []):
            _validate(value, child, root)
    for key in ("anyOf", "oneOf"):
        choices = schema.get(key)
        if choices:
            errors: list[AssertionError] = []
            for child in choices:
                try:
                    _validate(value, child, root)
                    break
                except AssertionError as error:
                    errors.append(error)
            else:
                raise AssertionError(f"value does not match {key}: {errors[0]}")
    expected = schema.get("type")
    if expected is not None:
        types = expected if isinstance(expected, list) else [expected]
        compatible = {
            "object": lambda item: isinstance(item, dict),
            "array": lambda item: isinstance(item, list),
            "string": lambda item: isinstance(item, str),
            "boolean": lambda item: isinstance(item, bool),
            "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
            "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
            "null": lambda item: item is None,
        }
        assert any(compatible.get(kind, lambda item: True)(value) for kind in types), (value, types)
    if "enum" in schema:
        assert value in schema["enum"], (value, schema["enum"])
    if "const" in schema:
        assert value == schema["const"], (value, schema["const"])
    if isinstance(value, dict):
        for key in schema.get("required", []):
            assert key in value, f"missing required key {key}"
        if schema.get("additionalProperties") is False:
            allowed = set(schema.get("properties", {}))
            assert set(value) <= allowed, f"unexpected keys {set(value) - allowed}"
        for key, child in schema.get("properties", {}).items():
            if key in value:
                _validate(value[key], child, root)
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for item in value:
            _validate(item, schema["items"], root)


def validate_payload(value: dict[str, Any], schema_path: str, *, fallback_required: tuple[str, ...]) -> None:
    """Validate a concrete fake payload with a generated schema when present."""
    schema = _schema(schema_path)
    if schema is None:
        _fallback_payload(value, schema_path, fallback_required)
        return
    _validate(value, schema, schema)


def _object(value: Any, label: str) -> dict[str, Any]:
    assert isinstance(value, dict), f"{label} must be an object"
    return value


def _string(value: Any, label: str) -> None:
    assert isinstance(value, str), f"{label} must be a string"


def _turn(value: Any, label: str) -> None:
    turn = _object(value, label)
    _string(turn.get("id"), f"{label}.id")
    assert isinstance(turn.get("items"), list), f"{label}.items must be an array"
    _string(turn.get("status"), f"{label}.status")


def _thread(value: Any, label: str) -> None:
    thread = _object(value, label)
    _string(thread.get("id"), f"{label}.id")
    assert isinstance(thread.get("status"), dict), f"{label}.status must be an object"
    assert isinstance(thread.get("turns"), list), f"{label}.turns must be an array"


def _fallback_payload(value: Any, schema_path: str, fallback_required: tuple[str, ...]) -> None:
    """Validate the nested protocol contract when generated schemas are absent."""
    payload = _object(value, schema_path)
    for key in fallback_required:
        assert key in payload, f"missing required key {key}"
    if schema_path == "JSONRPCRequest.json":
        assert isinstance(payload.get("id"), (str, int)) and not isinstance(payload.get("id"), bool)
        _string(payload.get("method"), "JSON-RPC request.method")
        assert isinstance(payload.get("params"), dict), "JSON-RPC request.params must be an object"
    elif schema_path == "JSONRPCResponse.json":
        assert isinstance(payload.get("id"), (str, int)) and not isinstance(payload.get("id"), bool)
    elif schema_path == "JSONRPCNotification.json":
        _string(payload.get("method"), "JSON-RPC notification.method")
    elif schema_path == "v1/InitializeResponse.json":
        for key in ("codexHome", "platformFamily", "platformOs", "userAgent"):
            _string(payload.get(key), f"initialize.{key}")
        assert payload["codexHome"].startswith("/"), "initialize.codexHome must be absolute"
    elif schema_path == "v2/GetAccountResponse.json":
        assert isinstance(payload.get("requiresOpenaiAuth"), bool)
        account = payload.get("account")
        assert account is None or isinstance(account, dict)
        if isinstance(account, dict):
            account_type = account.get("type")
            assert account_type in {"apiKey", "chatgpt", "amazonBedrock"}
            if account_type == "chatgpt":
                assert isinstance(account.get("email"), (str, type(None)))
                _string(account.get("planType"), "account.planType")
    elif schema_path == "v2/ConfigReadResponse.json":
        assert isinstance(payload.get("config"), dict), "config/read.config must be an object"
        assert isinstance(payload.get("origins"), dict), "config/read.origins must be an object"
    elif schema_path == "v2/SkillsListResponse.json":
        data = payload.get("data")
        assert isinstance(data, list), "skills/list.data must be an array"
        for index, entry in enumerate(data):
            entry = _object(entry, f"skills/list.data[{index}]")
            _string(entry.get("cwd"), f"skills/list.data[{index}].cwd")
            assert isinstance(entry.get("errors"), list), f"skills/list.data[{index}].errors must be an array"
            for error in entry["errors"]:
                error = _object(error, "skills/list error")
                _string(error.get("message"), "skills/list error.message")
                _string(error.get("path"), "skills/list error.path")
            assert isinstance(entry.get("skills"), list), f"skills/list.data[{index}].skills must be an array"
            for skill in entry["skills"]:
                skill = _object(skill, "skill")
                for key in ("name", "description", "path", "scope"):
                    _string(skill.get(key), f"skill.{key}")
                assert isinstance(skill.get("enabled"), bool), "skill.enabled must be a boolean"
                assert skill["scope"] in {"user", "repo", "system", "admin"}
    elif schema_path == "v2/ThreadStartResponse.json":
        _thread(payload.get("thread"), "thread/start.thread")
        for key in ("approvalPolicy", "approvalsReviewer", "cwd", "model", "modelProvider"):
            _string(payload.get(key), f"thread/start.{key}")
        sandbox = _object(payload.get("sandbox"), "thread/start.sandbox")
        _string(sandbox.get("type"), "thread/start.sandbox.type")
    elif schema_path == "v2/TurnStartResponse.json":
        _turn(payload.get("turn"), "turn/start.turn")
    elif schema_path == "CommandExecutionRequestApprovalResponse.json":
        assert payload.get("decision") in {"accept", "decline", "cancel"}
    elif schema_path == "CommandExecutionRequestApprovalParams.json":
        for key in ("itemId", "threadId", "turnId"):
            _string(payload.get(key), f"approval.{key}")
        assert isinstance(payload.get("startedAtMs"), int) and not isinstance(payload.get("startedAtMs"), bool)
    elif schema_path == "v2/AgentMessageDeltaNotification.json":
        for key in ("delta", "itemId", "threadId", "turnId"):
            _string(payload.get(key), f"agent message.{key}")
    elif schema_path == "v2/ItemStartedNotification.json":
        for key in ("threadId", "turnId"):
            _string(payload.get(key), f"item/started.{key}")
        assert isinstance(payload.get("startedAtMs"), int) and not isinstance(payload.get("startedAtMs"), bool)
        assert isinstance(payload.get("item"), dict), "item/started.item must be an object"
    elif schema_path == "v2/TurnCompletedNotification.json":
        _string(payload.get("threadId"), "turn/completed.threadId")
        _turn(payload.get("turn"), "turn/completed.turn")
    elif schema_path == "v2/ServerRequestResolvedNotification.json":
        _string(payload.get("requestId"), "serverRequest/resolved.requestId")
        _string(payload.get("threadId"), "serverRequest/resolved.threadId")


_REQUEST_PARAMETER_SCHEMAS = {
    "initialize": ("v1/InitializeParams.json", ("clientInfo",)),
    "account/read": ("v2/GetAccountParams.json", ()),
    "config/read": ("v2/ConfigReadParams.json", ()),
    "skills/extraRoots/set": ("v2/SkillsExtraRootsSetParams.json", ("extraRoots",)),
    "skills/list": ("v2/SkillsListParams.json", ()),
    "thread/start": ("v2/ThreadStartParams.json", ()),
    "turn/start": ("v2/TurnStartParams.json", ("threadId", "input")),
    "turn/interrupt": ("v2/TurnInterruptParams.json", ("threadId", "turnId")),
}


def _fallback_request_params(method: str, params: dict[str, Any]) -> None:
    """Check the protocol fields this test harness actually relies on."""
    if method == "initialize":
        info = params.get("clientInfo")
        assert isinstance(info, dict), "initialize.clientInfo must be an object"
        assert isinstance(info.get("name"), str), "initialize.clientInfo.name must be a string"
        assert isinstance(info.get("version"), str), "initialize.clientInfo.version must be a string"
        capabilities = params.get("capabilities")
        assert capabilities is None or isinstance(capabilities, dict)
        if isinstance(capabilities, dict) and "experimentalApi" in capabilities:
            assert isinstance(capabilities["experimentalApi"], bool)
    elif method == "initialized":
        assert params == {}, "initialized must use empty params"
    elif method == "account/read":
        assert set(params) <= {"refreshToken"}
        if "refreshToken" in params:
            assert isinstance(params["refreshToken"], bool)
    elif method == "config/read":
        assert set(params) <= {"cwd", "includeLayers"}
        assert isinstance(params.get("cwd"), (str, type(None)))
        assert params.get("includeLayers") is False
    elif method == "skills/extraRoots/set":
        roots = params.get("extraRoots")
        assert isinstance(roots, list) and all(isinstance(root, str) and root.startswith("/") for root in roots)
    elif method == "skills/list":
        assert set(params) <= {"cwds", "forceReload"}
        if "cwds" in params:
            assert isinstance(params["cwds"], list) and all(isinstance(cwd, str) for cwd in params["cwds"])
        if "forceReload" in params:
            assert isinstance(params["forceReload"], bool)
    elif method == "thread/start":
        _string(params.get("cwd"), "thread/start.cwd")
        assert isinstance(params.get("ephemeral"), bool), "thread/start.ephemeral must be a boolean"
        roots = params.get("runtimeWorkspaceRoots")
        assert isinstance(roots, list) and all(isinstance(root, str) and root.startswith("/") for root in roots)
        assert params.get("sandbox") in {"workspace-write", "danger-full-access", "read-only"}
        _string(params.get("approvalPolicy"), "thread/start.approvalPolicy")
        assert isinstance(params.get("config"), dict), "thread/start.config must be an object"
    elif method == "turn/start":
        _string(params.get("threadId"), "turn/start.threadId")
        input_items = params.get("input")
        assert isinstance(input_items, list) and input_items, "turn/start.input must be a nonempty array"
        for item in input_items:
            item = _object(item, "turn/start input item")
            if item.get("type") == "skill":
                _string(item.get("name"), "turn/start skill.name")
                _string(item.get("path"), "turn/start skill.path")
            elif item.get("type") == "text":
                _string(item.get("text"), "turn/start text.text")
            else:
                raise AssertionError("turn/start input item type is unsupported")
        _string(params.get("cwd"), "turn/start.cwd")
        policy = _object(params.get("sandboxPolicy"), "turn/start.sandboxPolicy")
        _string(policy.get("type"), "turn/start.sandboxPolicy.type")
        roots = policy.get("writableRoots")
        assert isinstance(roots, list) and all(isinstance(root, str) and root.startswith("/") for root in roots)
        assert isinstance(policy.get("networkAccess"), bool)
        _string(params.get("approvalPolicy"), "turn/start.approvalPolicy")
        assert isinstance(params.get("outputSchema"), dict), "turn/start.outputSchema must be an object"
    elif method == "turn/interrupt":
        assert isinstance(params.get("threadId"), str)
        assert isinstance(params.get("turnId"), str)


def validate_method_params(method: str, params: Any) -> None:
    """Validate parameters for every App Server method our fakes exchange."""
    assert isinstance(params, dict), f"{method}.params must be an object"
    if method == "initialized":
        _fallback_request_params(method, params)
        return
    detail = _REQUEST_PARAMETER_SCHEMAS.get(method)
    if detail is None:
        return
    schema_path, required = detail
    schema = _schema(schema_path)
    if schema is None:
        for key in required:
            assert key in params, f"missing required key {key}"
        _fallback_request_params(method, params)
        return
    _validate(params, schema, schema)


def _validate_client_notification(message: dict[str, Any]) -> None:
    """Accept only client notifications declared by the App Server schema."""
    validate_payload(message, "JSONRPCNotification.json", fallback_required=("method",))
    schema = _schema("ClientNotification.json")
    if schema is not None:
        _validate(message, schema, schema)
    else:
        assert message.get("method") == "initialized", "unknown client notification"
    validate_method_params(str(message["method"]), message.get("params"))


def validate_jsonrpc_fixture(
    messages: list[dict[str, Any]],
    responses: dict[str, dict[str, Any]],
    emitted: list[dict[str, Any]],
) -> None:
    """Validate every request, response, and notification emitted by a fake."""
    for message in messages:
        if "id" in message and "method" in message:
            validate_payload(message, "JSONRPCRequest.json", fallback_required=("id", "method"))
            validate_method_params(str(message["method"]), message.get("params"))
        elif "id" in message and "result" in message:
            validate_payload(message, "JSONRPCResponse.json", fallback_required=("id", "result"))
            validate_payload(message["result"], "CommandExecutionRequestApprovalResponse.json", fallback_required=("decision",))
        elif "method" in message:
            _validate_client_notification(message)
    response_schemas = {
        "initialize": ("v1/InitializeResponse.json", ("codexHome", "platformFamily", "platformOs", "userAgent")),
        "account/read": ("v2/GetAccountResponse.json", ("requiresOpenaiAuth",)),
        "config/read": ("v2/ConfigReadResponse.json", ("config", "origins")),
        "skills/extraRoots/set": ("v2/SkillsExtraRootsSetResponse.json", ()),
        "skills/list": ("v2/SkillsListResponse.json", ("data",)),
        "thread/start": ("v2/ThreadStartResponse.json", ("thread", "approvalPolicy", "approvalsReviewer", "cwd", "model", "modelProvider", "sandbox")),
        "turn/start": ("v2/TurnStartResponse.json", ("turn",)),
        "turn/interrupt": ("v2/TurnInterruptResponse.json", ()),
    }
    for method, response in responses.items():
        detail = response_schemas.get(method)
        if detail is not None:
            schema_path, required = detail
            validate_payload(response, schema_path, fallback_required=required)
    for message in emitted:
        if "id" in message and "result" in message:
            validate_payload(message, "JSONRPCResponse.json", fallback_required=("id", "result"))
        elif message.get("method") == "item/commandExecution/requestApproval":
            validate_payload(message, "JSONRPCRequest.json", fallback_required=("id", "method"))
            validate_payload(message.get("params", {}), "CommandExecutionRequestApprovalParams.json", fallback_required=("itemId", "threadId", "turnId", "startedAtMs"))
        elif message.get("method") == "item/agentMessage/delta":
            validate_payload(message, "JSONRPCNotification.json", fallback_required=("method",))
            validate_payload(message.get("params", {}), "v2/AgentMessageDeltaNotification.json", fallback_required=("delta", "itemId", "threadId", "turnId"))
        elif message.get("method") == "item/started":
            validate_payload(message, "JSONRPCNotification.json", fallback_required=("method",))
            validate_payload(message.get("params", {}), "v2/ItemStartedNotification.json", fallback_required=("item", "startedAtMs", "threadId", "turnId"))
        elif message.get("method") == "turn/completed":
            validate_payload(message, "JSONRPCNotification.json", fallback_required=("method",))
            validate_payload(message.get("params", {}), "v2/TurnCompletedNotification.json", fallback_required=("threadId", "turn"))
        elif message.get("method") == "serverRequest/resolved":
            validate_payload(message, "JSONRPCNotification.json", fallback_required=("method",))
            validate_payload(message.get("params", {}), "v2/ServerRequestResolvedNotification.json", fallback_required=("requestId", "threadId"))
        elif "method" in message:
            validate_payload(message, "JSONRPCNotification.json", fallback_required=("method",))
