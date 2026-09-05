#!/usr/bin/env python3
"""Regenerate the Codex skills from the adjacent Claude SSoT plus exact overlays."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--source", type=Path, default=PLUGIN_ROOT.parent / "crystallize")
    return parser.parse_args()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix().encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        contents = path.read_bytes()
        digest.update(len(contents).to_bytes(8, "big"))
        digest.update(contents)
    return digest.hexdigest()


def build(source: Path, destination: Path) -> None:
    shutil.copytree(source / "skills", destination / "skills")
    for patch_path in sorted((PLUGIN_ROOT / "overrides" / "patches").glob("*.patch")):
        result = subprocess.run(
            ["patch", "-p1", "--batch", "--fuzz=0", "-i", str(patch_path)],
            cwd=destination,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            details = (result.stdout + result.stderr).strip()
            raise SystemExit(f"stale Codex overlay: {patch_path.name}\n{details}")
    extra_root = PLUGIN_ROOT / "overrides" / "files"
    if extra_root.is_dir():
        shutil.copytree(extra_root, destination, dirs_exist_ok=True)


def compare_trees(expected: Path, actual: Path) -> list[str]:
    expected_files = {p.relative_to(expected) for p in expected.rglob("*") if p.is_file()}
    actual_files = {p.relative_to(actual) for p in actual.rglob("*") if p.is_file()}
    problems = [f"missing: {path}" for path in sorted(expected_files - actual_files)]
    problems += [f"unexpected: {path}" for path in sorted(actual_files - expected_files)]
    for relative in sorted(expected_files & actual_files):
        if (expected / relative).read_bytes() != (actual / relative).read_bytes():
            problems.append(f"changed: {relative}")
    return problems


def lock_data(source: Path, generated_skills: Path) -> dict[str, object]:
    source_manifest = source / ".claude-plugin" / "plugin.json"
    source_data = json.loads(source_manifest.read_text(encoding="utf-8"))
    return {
        "schema_version": 1,
        "source_version": source_data["version"],
        "source_manifest_sha256": file_hash(source_manifest),
        "source_skills_sha256": tree_hash(source / "skills"),
        "overrides_sha256": tree_hash(PLUGIN_ROOT / "overrides"),
        "generated_skills_sha256": tree_hash(generated_skills),
    }


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    source_manifest = source / ".claude-plugin" / "plugin.json"
    if not source_manifest.is_file() or not (source / "skills").is_dir():
        raise SystemExit(f"Claude SSoT plugin not found: {source}")

    with tempfile.TemporaryDirectory(prefix="crystallize-codex-sync-") as temp_dir:
        generated_root = Path(temp_dir)
        build(source, generated_root)
        expected_skills = generated_root / "skills"
        expected_lock = lock_data(source, expected_skills)

        if args.write:
            destination = PLUGIN_ROOT / "skills"
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(expected_skills, destination)
            (PLUGIN_ROOT / "port.lock.json").write_text(
                json.dumps(expected_lock, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            manifest_path = PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["version"] = expected_lock["source_version"]
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("crystallize-codex regenerated from Claude SSoT")
            return 0

        problems = compare_trees(expected_skills, PLUGIN_ROOT / "skills")
        lock_path = PLUGIN_ROOT / "port.lock.json"
        if not lock_path.is_file():
            problems.append("missing: port.lock.json")
        else:
            actual_lock = json.loads(lock_path.read_text(encoding="utf-8"))
            if actual_lock != expected_lock:
                problems.append("changed: port.lock.json")
        manifest = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        if manifest.get("version") != expected_lock["source_version"]:
            problems.append("manifest version differs from Claude SSoT")
        if problems:
            print("crystallize-codex is out of sync:")
            for problem in problems:
                print(f"- {problem}")
            return 1
        print("crystallize-codex is in sync with Claude SSoT")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
