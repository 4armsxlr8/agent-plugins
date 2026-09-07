#!/usr/bin/env python3
"""CLI regression tests for the Codex port validator."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


class ValidatePortCliTests(unittest.TestCase):
    def run_validator(self, fixture_root: Path, codex_home: Path) -> subprocess.CompletedProcess[str]:
        official_review_skill = codex_home / "skills" / ".system" / "review-agent" / "SKILL.md"
        official_review_skill.parent.mkdir(parents=True)
        official_review_skill.write_text("official review-agent fixture\n", encoding="utf-8")
        environment = os.environ.copy()
        environment["CODEX_HOME"] = str(codex_home)
        return subprocess.run(
            [sys.executable, str(fixture_root / "scripts" / "validate_port.py")],
            text=True,
            capture_output=True,
            env=environment,
            check=False,
        )

    def copy_fixture(self, temporary_directory: str) -> Path:
        fixture_root = Path(temporary_directory) / "crystallize-codex"
        shutil.copytree(PLUGIN_ROOT, fixture_root)
        return fixture_root

    def test_cli_rejects_legacy_find_unknowns_skill_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture_root = self.copy_fixture(temporary_directory)
            for skill_name in ("spec", "plan-create"):
                shutil.rmtree(fixture_root / "skills" / skill_name, ignore_errors=True)

            find_unknowns = fixture_root / "skills" / "find-unknowns"
            if not find_unknowns.is_dir():
                source_spec = PLUGIN_ROOT.parent / "crystallize" / "skills" / "spec"
                shutil.copytree(source_spec, find_unknowns)
                skill_path = find_unknowns / "SKILL.md"
                skill_path.write_text(
                    skill_path.read_text(encoding="utf-8").replace("name: spec\n", "name: find-unknowns\n", 1),
                    encoding="utf-8",
                )

            result = self.run_validator(fixture_root, Path(temporary_directory) / "codex-home")

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("required skills missing", result.stdout)
            self.assertIn("legacy find-unknowns skill must be removed", result.stdout)

    def test_cli_rejects_evaluator_schema_breakdown_key_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture_root = self.copy_fixture(temporary_directory)
            schema_path = fixture_root / "skills" / "plan-evaluator" / "output.schema.json"
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            breakdown = schema["properties"]["quality"]["properties"]["breakdown"]
            drifted_key = next(iter(breakdown["properties"]))
            drifted_property = breakdown["properties"].pop(drifted_key)
            breakdown["properties"]["__drifted_key__"] = drifted_property
            breakdown["required"] = [
                "__drifted_key__" if key == drifted_key else key for key in breakdown["required"]
            ]
            schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            result = self.run_validator(fixture_root, Path(temporary_directory) / "codex-home")

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("breakdown keys do not match eval-schema.json", result.stdout)

    def test_cli_rejects_legacy_plan_implement_phase_one_heading(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture_root = self.copy_fixture(temporary_directory)
            skill_path = fixture_root / "skills" / "plan-implement" / "SKILL.md"
            text = skill_path.read_text(encoding="utf-8")
            current_heading = "## フェーズ1: plan / spec 受領と Deviations 契約"
            legacy_heading = "## フェーズ1: plan 受領"
            if current_heading in text:
                text = text.replace(current_heading, legacy_heading, 1)
            skill_path.write_text(text, encoding="utf-8")

            result = self.run_validator(fixture_root, Path(temporary_directory) / "codex-home")

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("plan-implement review preflight headings are incomplete", result.stdout)


if __name__ == "__main__":
    unittest.main()
