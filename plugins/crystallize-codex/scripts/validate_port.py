#!/usr/bin/env python3
"""Validate Codex-specific invariants that the generic plugin validator cannot see."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SKILLS = frozenset(
    {
        "code-generator",
        "diff-review",
        "html-report",
        "issue-create",
        "plan",
        "plan-commit",
        "plan-evaluator",
        "plan-implement",
        "question-evaluator",
        "spec",
        "tdd",
        "test-generator",
    }
)
FORBIDDEN = (
    "$ARGUMENTS",
    "AskUserQuestion",
    "Skill ツール",
    "Skill tool",
    "Explore subagent",
    "WebSearch",
    "WebFetch",
    "context: fork",
    "model: sonnet",
    "claude.ai",
    "orca-cli",
    "/find-unknowns",
    "/code-review",
    "git add -A",
    "git reset --",
)


def frontmatter_keys(text: str) -> set[str]:
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        return set()
    block = text[4:].split("\n---\n", 1)[0]
    return {match.group(1) for line in block.splitlines() if (match := re.match(r"^([a-zA-Z0-9_-]+):", line))}


def eval_schema_breakdown_keys(schema: object) -> set[str] | None:
    if not isinstance(schema, dict):
        return None
    entries = schema.get("breakdown_keys")
    if not isinstance(entries, list):
        return None
    keys: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("key"), str):
            return None
        keys.append(entry["key"])
    if len(set(keys)) != len(keys):
        return None
    return set(keys)


def output_schema_breakdown_keys(schema: object) -> tuple[set[str], set[str]] | None:
    if not isinstance(schema, dict):
        return None
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return None
    quality = properties.get("quality")
    if not isinstance(quality, dict):
        return None
    quality_properties = quality.get("properties")
    if not isinstance(quality_properties, dict):
        return None
    breakdown = quality_properties.get("breakdown")
    if not isinstance(breakdown, dict):
        return None
    breakdown_properties = breakdown.get("properties")
    required = breakdown.get("required")
    if not isinstance(breakdown_properties, dict) or not isinstance(required, list):
        return None
    if not all(isinstance(key, str) for key in required):
        return None
    return set(breakdown_properties), set(required)


def main() -> int:
    errors: list[str] = []
    manifest = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    if manifest.get("name") != "crystallize-codex":
        errors.append("manifest name must be crystallize-codex")
    if manifest.get("skills") != "./skills/":
        errors.append("manifest skills must be ./skills/")

    skill_dirs = sorted(path.parent for path in (PLUGIN_ROOT / "skills").glob("*/SKILL.md"))
    skill_names = {skill_dir.name for skill_dir in skill_dirs}
    if len(skill_dirs) != len(EXPECTED_SKILLS):
        errors.append(f"expected {len(EXPECTED_SKILLS)} skills, found {len(skill_dirs)}")
    missing_skills = sorted(EXPECTED_SKILLS - skill_names)
    if missing_skills:
        errors.append(f"required skills missing: {', '.join(missing_skills)}")
    if (PLUGIN_ROOT / "skills" / "find-unknowns").exists():
        errors.append("legacy find-unknowns skill must be removed")

    for skill_dir in skill_dirs:
        skill_path = skill_dir / "SKILL.md"
        text = skill_path.read_text(encoding="utf-8")
        keys = frontmatter_keys(text)
        if keys != {"name", "description"}:
            errors.append(f"{skill_path.relative_to(PLUGIN_ROOT)} frontmatter keys: {sorted(keys)}")
        name_match = re.search(r"^name:\s*(.+)$", text, re.MULTILINE)
        if not name_match or name_match.group(1).strip() != skill_dir.name:
            errors.append(f"{skill_path.relative_to(PLUGIN_ROOT)} name does not match directory")
        for token in FORBIDDEN:
            if token in text:
                errors.append(f"{skill_path.relative_to(PLUGIN_ROOT)} contains Claude-only token: {token}")
        if re.search(r"(?<!\.)/plan-[a-z]", text):
            errors.append(f"{skill_path.relative_to(PLUGIN_ROOT)} contains a Claude slash command")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            if target.startswith(("http://", "https://", "#")) or "<" in target:
                continue
            resolved = (skill_dir / target.split("#", 1)[0]).resolve()
            if not resolved.exists():
                errors.append(f"{skill_path.relative_to(PLUGIN_ROOT)} missing link target: {target}")

    for name in ("code-generator", "test-generator"):
        policy = PLUGIN_ROOT / "skills" / name / "agents" / "openai.yaml"
        if not policy.is_file() or "allow_implicit_invocation: false" not in policy.read_text(encoding="utf-8"):
            errors.append(f"{name} must disable implicit invocation")

    for name in ("question-evaluator", "plan-evaluator"):
        schema_path = PLUGIN_ROOT / "skills" / name / "output.schema.json"
        if not schema_path.is_file():
            errors.append(f"{name} is missing output.schema.json")
            continue
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            errors.append(f"{name} output.schema.json is invalid JSON")
            continue
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            errors.append(f"{name} output.schema.json must declare Draft 2020-12")
        eval_schema_path = PLUGIN_ROOT / "skills" / name / "eval-schema.json"
        if not eval_schema_path.is_file():
            errors.append(f"{name} is missing eval-schema.json")
            continue
        try:
            eval_schema = json.loads(eval_schema_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            errors.append(f"{name} eval-schema.json is invalid JSON")
            continue
        expected_breakdown_keys = eval_schema_breakdown_keys(eval_schema)
        actual_breakdown = output_schema_breakdown_keys(schema)
        if expected_breakdown_keys is None or actual_breakdown is None:
            errors.append(f"{name} evaluator schema breakdown keys are malformed")
        else:
            actual_properties, actual_required = actual_breakdown
            if actual_properties != expected_breakdown_keys or actual_required != expected_breakdown_keys:
                errors.append(f"{name} output.schema.json breakdown keys do not match eval-schema.json")

    runtime_text = (PLUGIN_ROOT / "references" / "codex-runtime.md").read_text(encoding="utf-8")
    role_owners = {
        "question-evaluator": "question-evaluator",
        "plan-evaluator": "plan-evaluator",
        "test-generator": "test-generator",
        "code-generator": "code-generator",
        "code-review": "plan-implement",
        "html-report": "html-report",
        "diff-review": "diff-review",
    }
    for role, skill_name in role_owners.items():
        marker = f"CRYSTALLIZE_CODEX_ROLE={role}"
        skill_text = (PLUGIN_ROOT / "skills" / skill_name / "SKILL.md").read_text(encoding="utf-8")
        if marker not in runtime_text or marker not in skill_text:
            errors.append(f"role marker is inconsistent for {role}")
    legacy_markers = re.findall(r"CRYSTALLIZE_(?!CODEX_ROLE=)[A-Z_]+", "\n".join(
        path.read_text(encoding="utf-8") for path in (PLUGIN_ROOT / "skills").glob("*/SKILL.md")
    ))
    if legacy_markers:
        errors.append(f"legacy role markers remain: {sorted(set(legacy_markers))}")

    review_text = (PLUGIN_ROOT / "skills" / "plan-implement" / "SKILL.md").read_text(encoding="utf-8")
    review_requirements = (
        "CODEX_HOME",
        "skills/.system/review-agent/SKILL.md",
        "realpath",
        "書込み前preflight",
        "resolved_review_skill",
        "フェーズ3はこの値だけを使い",
        "別パスを再解決しない",
        "plan / production codeへの一切の書込み前に停止・報告する",
        'model: "gpt-5.6-sol"',
        'reasoning_effort: "xhigh"',
        'fork_turns: "none"',
        "review_target_diff",
        "verification",
        "output_contract",
        "read-only",
        "defect-first",
        "P0-P3",
        "No findings.",
        "汎用レビュープロンプトや同一コンテキストへフォールバックせず",
    )
    for token in review_requirements:
        if token not in review_text:
            errors.append(f"plan-implement review contract missing: {token}")
    phase1_heading = "## フェーズ1: plan / spec 受領と Deviations 契約"
    phase2_heading = "## フェーズ2: 実装"
    phase3_heading = "## フェーズ3: 機械ゲート"
    try:
        phase1_start = review_text.index(phase1_heading)
        phase2_start = review_text.index(phase2_heading)
        phase3_start = review_text.index(phase3_heading)
        preflight_start = review_text.index("**書込み前preflight**")
    except ValueError:
        errors.append("plan-implement review preflight headings are incomplete")
    else:
        if not phase1_start < preflight_start < phase2_start:
            errors.append("review-agent preflight must run in phase 1 before phase 2 writes")
        if "resolved_review_skill" not in review_text[phase1_start:phase2_start]:
            errors.append("phase 1 must retain resolved_review_skill")
        if "resolved_review_skill" not in review_text[phase3_start:]:
            errors.append("phase 3 must use the retained resolved_review_skill")
    codex_home_configured = "CODEX_HOME" in os.environ
    codex_home = Path(os.environ["CODEX_HOME"]).expanduser() if codex_home_configured else Path.home() / ".codex"
    official_review_skill = codex_home / "skills" / ".system" / "review-agent" / "SKILL.md"
    # An explicitly configured home is the runtime contract: fail closed when
    # its official review skill is absent or unusable.  For the default home,
    # only a genuinely absent path entry is optional so the source distribution
    # remains portable; dangling symlinks are validated below as unusable.
    if codex_home_configured or official_review_skill.exists() or official_review_skill.is_symlink():
        try:
            resolved_review_skill = official_review_skill.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            errors.append(f"official review-agent SKILL cannot be resolved: {error}")
        else:
            if not resolved_review_skill.is_file() or not os.access(resolved_review_skill, os.R_OK):
                errors.append("official review-agent SKILL exists but is not a readable file")
    review_docs = {
        "plan-implement": review_text,
        "codex-runtime": runtime_text,
        "README": (PLUGIN_ROOT / "README.md").read_text(encoding="utf-8"),
    }
    user_path_pattern = re.compile(r"(?:/Users/|/home/|/root/|[A-Za-z]:[\\/])")
    for doc_name, doc_text in review_docs.items():
        if "kyouyagenki" in doc_text or user_path_pattern.search(doc_text):
            errors.append(f"{doc_name} contains a user-specific absolute path")
    if (PLUGIN_ROOT / "skills" / "review-agent" / "SKILL.md").exists():
        errors.append("official review-agent SKILL must not be copied into the plugin")

    commit_text = (PLUGIN_ROOT / "skills" / "plan-commit" / "SKILL.md").read_text(encoding="utf-8")
    safety_markers = ("backup/", "コミットに失敗した場合", "復元してbyte一致")
    if any(marker not in commit_text for marker in safety_markers):
        errors.append("plan-commit must preserve and restore the full plan backup on commit failure")
    elif not (
        commit_text.index("backup/")
        < commit_text.index("**plan の削除**")
        < commit_text.index("git commit -F")
        < commit_text.index("コミットに失敗した場合")
    ):
        errors.append("plan-commit backup/delete/commit/recovery order is invalid")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("crystallize-codex port invariants are valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
