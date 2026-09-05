#!/usr/bin/env python3
"""Capture current generated skill differences as validated, atomic Codex overlays."""

from __future__ import annotations

import argparse
import difflib
import shutil
import subprocess
import tempfile
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=PLUGIN_ROOT.parent / "crystallize")
    return parser.parse_args()


def file_set(root: Path) -> set[Path]:
    return {path.relative_to(root) for path in root.rglob("*") if path.is_file()}


def compare_trees(expected: Path, actual: Path) -> list[str]:
    expected_files = file_set(expected)
    actual_files = file_set(actual)
    problems = [f"missing: {path}" for path in sorted(expected_files - actual_files)]
    problems += [f"unexpected: {path}" for path in sorted(actual_files - expected_files)]
    for relative in sorted(expected_files & actual_files):
        if (expected / relative).read_bytes() != (actual / relative).read_bytes():
            problems.append(f"changed: {relative}")
    return problems


def generate(source_skills: Path, generated_skills: Path, overlay_root: Path) -> tuple[int, int]:
    patches_dir = overlay_root / "patches"
    files_dir = overlay_root / "files"
    patches_dir.mkdir(parents=True)
    files_dir.mkdir(parents=True)

    source_files = file_set(source_skills)
    generated_files = file_set(generated_skills)
    deleted = source_files - generated_files
    if deleted:
        names = "\n".join(str(path) for path in sorted(deleted))
        raise SystemExit(f"Deleted source files need an explicit sync rule:\n{names}")

    patch_count = 0
    for relative in sorted(source_files & generated_files):
        source_bytes = (source_skills / relative).read_bytes()
        generated_bytes = (generated_skills / relative).read_bytes()
        if source_bytes == generated_bytes:
            continue
        try:
            source_text = source_bytes.decode("utf-8").splitlines(keepends=True)
            generated_text = generated_bytes.decode("utf-8").splitlines(keepends=True)
        except UnicodeDecodeError as error:
            raise SystemExit(f"Binary overrides are not supported: {relative}") from error
        patch_text = "".join(
            difflib.unified_diff(
                source_text,
                generated_text,
                fromfile=f"a/skills/{relative.as_posix()}",
                tofile=f"b/skills/{relative.as_posix()}",
            )
        )
        if not patch_text:
            raise SystemExit(f"Empty patch generated for changed file: {relative}")
        patch_name = "__".join(relative.parts) + ".patch"
        (patches_dir / patch_name).write_text(patch_text, encoding="utf-8")
        patch_count += 1

    extra_count = 0
    for relative in sorted(generated_files - source_files):
        destination = files_dir / "skills" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(generated_skills / relative, destination)
        extra_count += 1
    return patch_count, extra_count


def validate(source_skills: Path, generated_skills: Path, overlay_root: Path, temp_root: Path) -> None:
    rebuilt_root = temp_root / "rebuilt"
    shutil.copytree(source_skills, rebuilt_root / "skills")
    for patch_path in sorted((overlay_root / "patches").glob("*.patch")):
        result = subprocess.run(
            ["patch", "-p1", "--batch", "--fuzz=0", "-i", str(patch_path)],
            cwd=rebuilt_root,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            details = (result.stdout + result.stderr).strip()
            raise SystemExit(f"Generated overlay does not apply: {patch_path.name}\n{details}")
    shutil.copytree(overlay_root / "files", rebuilt_root, dirs_exist_ok=True)
    problems = compare_trees(generated_skills, rebuilt_root / "skills")
    if problems:
        raise SystemExit("Generated overlays do not reproduce skills:\n" + "\n".join(problems))


def replace_atomically(new_overrides: Path) -> None:
    target = PLUGIN_ROOT / "overrides"
    backup = PLUGIN_ROOT / ".overrides-backup"
    if backup.exists():
        raise SystemExit(f"Refusing to overwrite recovery directory: {backup}")
    if target.exists():
        target.rename(backup)
    try:
        new_overrides.rename(target)
    except Exception:
        if backup.exists() and not target.exists():
            backup.rename(target)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def main() -> int:
    args = parse_args()
    source_skills = args.source.resolve() / "skills"
    generated_skills = PLUGIN_ROOT / "skills"
    if not source_skills.is_dir():
        raise SystemExit(f"Claude SSoT skills not found: {source_skills}")

    with tempfile.TemporaryDirectory(prefix=".crystallize-overlays-", dir=PLUGIN_ROOT) as temp_dir:
        temp_root = Path(temp_dir)
        new_overrides = temp_root / "overrides"
        patch_count, extra_count = generate(source_skills, generated_skills, new_overrides)
        validate(source_skills, generated_skills, new_overrides, temp_root)
        replace_atomically(new_overrides)

    print(f"captured {patch_count} patches")
    print(f"captured {extra_count} extra files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
