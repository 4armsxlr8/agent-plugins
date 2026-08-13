# agent-plugins

日本語版はこちら → [README.ja.md](README.ja.md)

A public collection of Claude Code plugins and skills, also packaged in Codex plugin format.

## Installation

```
/plugin marketplace add 4armsxlr8/agent-plugins
/plugin install study-loop@agent-plugins
/plugin install flutter-riverpod-guardrails@agent-plugins
```

## Plugins

### study-loop — step-by-step learning for any topic

Turns "I want to study X" into a loop instead of a wall of explanation: level diagnosis → generate an assignment file → the user fills in the answer → grade → feedback → next assignment. Topic-agnostic — programming, languages, math, history, exam prep, anything.

Main components:

- **`skills/study-loop/SKILL.md`** — the orchestration skill. Runs a 4-phase loop (setup → diagnostic → curriculum generation → lesson loop) and writes session state as Markdown under `.study/<topic-slug>/` (progress dashboard, curriculum, glossary, feedback rules, insights log).
- **Evidence-based design** — every design decision cites a meta-analysis or systematic review, documented with effect sizes and sources in `skills/study-loop/references/learning-science.md`. For example: feedback quality (Hattie & Timperley, *d* ≈ 0.70–1.00), retrieval practice / testing effect (Roediger & Karpicke, *d* ≈ 0.50–0.80), the self-explanation effect (Bisra et al., *g* ≈ 0.55), worked-examples fading (Sweller / Kalyuga, *d* ≈ 0.5–1.0), distributed practice / spacing (Cepeda et al., *d* ≈ 0.4–0.9), interleaved practice (Brunmair & Richter, *g* ≈ 0.42), and elaborative interrogation (Dunlosky et al., *d* ≈ 0.42).
- **Generator-Critic loop** — assignments are drafted by a Generator prompt and checked by a separate Critic pass before being shown to the user, to catch issues like answers leaked in comments.
- **`/study-ui`** — starts a local Flask web UI (`skills/study-loop/scripts/server.py`) bound to loopback only, for viewing lessons and filling in answers in the browser instead of editing Markdown directly. Optionally drives grading through a local Codex App Server session; `/study-ui-stop` shuts it down.

> **Note**: study-loop's skill instructions (`SKILL.md`) are currently written in Japanese, so the agent runs the loop most naturally in Japanese.

### flutter-riverpod-guardrails — Flutter + Riverpod architecture guardrail

Enforces Clean Architecture layering (Domain / Data / Application / Presentation) in Flutter + Riverpod projects and runs `dart analyze` before commits.

Main components:

- **`skills/flutter-riverpod-architecture/SKILL.md`** — documents the layer dependency rules (e.g. Domain must stay pure Dart with no Flutter/Riverpod/Firebase/http imports; Presentation must not import Data repositories directly) plus per-layer reference guides and a recommended directory structure.
- **`hooks/hooks.json`** — wires two hooks: a `PostToolUse` hook on Edit/Write that runs `scripts/check-architecture.sh` to flag layer violations in the file just changed, and a `PreToolUse` hook on Bash that runs `scripts/pre-commit-lint.sh` before `git commit` commands.
- **`scripts/check-architecture.sh`** — pattern-based checker for layer violations (forbidden imports per layer, `BuildContext`/`Navigator` usage in the wrong layer, function-style widgets in Presentation). Can also run standalone in scan mode: `./check-architecture.sh --scan <lib_directory>`.
- **`scripts/pre-commit-lint.sh`** — runs `dart analyze` before `git commit` and surfaces errors/warnings back to the agent.

## Local development

Test a plugin locally without installing it, from the repository root:

```bash
claude --plugin-dir ./plugins/study-loop
claude --plugin-dir ./plugins/flutter-riverpod-guardrails
```

Or register this checkout as a local marketplace:

```bash
/plugin marketplace add /path/to/agent-plugins
/plugin install study-loop@agent-plugins
/plugin install flutter-riverpod-guardrails@agent-plugins
```

Validate plugin manifests and hook definitions:

```bash
claude plugin validate ./plugins/study-loop
claude plugin validate ./plugins/flutter-riverpod-guardrails
```

## License

MIT — see [LICENSE](LICENSE).
