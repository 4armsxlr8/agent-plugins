# agent-plugins

日本語版はこちら → [README.ja.md](README.ja.md)

A public collection of Claude Code plugins and skills, also packaged in Codex plugin format.

## Installation

```
/plugin marketplace add 4armsxlr8/agent-plugins
/plugin install flutter-riverpod-guardrails@agent-plugins
```

## Plugins

### flutter-riverpod-guardrails — Flutter + Riverpod architecture guardrail

Enforces Clean Architecture layering (Domain / Data / Application / Presentation) in Flutter + Riverpod projects and runs `dart analyze` before commits.

Main components:

- **`skills/architecture/SKILL.md`** — documents the layer dependency rules (e.g. Domain must stay pure Dart with no Flutter/Riverpod/Firebase/http imports; Presentation must not import Data repositories directly) plus per-layer reference guides and a recommended directory structure.
- **`hooks/hooks.json`** — wires two hooks: a `PostToolUse` hook on Edit/Write that runs `scripts/check-architecture.sh` to flag layer violations in the file just changed, and a `PreToolUse` hook on Bash that runs `scripts/pre-commit-lint.sh` before `git commit` commands.
- **`scripts/check-architecture.sh`** — pattern-based checker for layer violations (forbidden imports per layer, `BuildContext`/`Navigator` usage in the wrong layer, function-style widgets in Presentation). Can also run standalone in scan mode: `./check-architecture.sh --scan <lib_directory>`.
- **`scripts/pre-commit-lint.sh`** — runs `dart analyze` before `git commit` and surfaces errors/warnings back to the agent.

### crystallize — plan-driven development flow

Packages a full personal development workflow: turn a vague request into confirmed decisions, crystallize those into a plan, and run the plan through three gates (mechanical / behavioral / exception) before it becomes a commit.

Main components:

- **`skills/issue-create`** — turns a chat aside (bug, idea, chore) into a GitHub issue from the repo's issue templates.
- **`skills/find-unknowns`** — pre-implementation alignment: surfaces and resolves unknowns with the user, writes a single plan file.
- **`skills/question-evaluator`** — audits `find-unknowns`' questions for false premises and false dilemmas in an isolated context before they reach the user.
- **`skills/plan-implement`** — drives implementation and the mechanical/behavioral/exception gates through to the commit handoff.
- **`skills/test-generator`** / **`skills/code-generator`** — the red and green sides of TDD, run as separate subagents so the same agent can't write both a test and the code that games it.
- **`skills/diff-review`** — an "exception viewer" that surfaces only risky hunks once behavior is confirmed, instead of asking a human to read every line.
- **`skills/html-report`** — turns long prose reports into a self-contained HTML page.
- **`skills/plan-commit`** — folds the finished plan into the commit message and deletes the plan file.
- **`skills/tdd`** — a reference for what makes a test worth keeping, forked from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT).

Plans and reports are written to `docs/crystallize/plans/` and `docs/crystallize/reports/` in the target repository.

## In development (not released)

### study-loop — step-by-step learning for any topic

Turns "I want to study X" into a loop instead of a wall of explanation: level diagnosis → assignment file → the user fills in the answer → grade → feedback → next assignment, with a local web UI. Lives under [`dev/study-loop`](dev/study-loop).

**Not usable yet.** It is intentionally excluded from the marketplace, so `/plugin install study-loop@agent-plugins` does not work, and its commands, file formats, and behavior may change without notice. If you want to peek at a work in progress anyway, you can load it from a clone with `claude --plugin-dir ./dev/study-loop` — at your own risk.

## Local development

Test a plugin locally without installing it, from the repository root:

```bash
claude --plugin-dir ./plugins/flutter-riverpod-guardrails
```

Or register this checkout as a local marketplace:

```bash
/plugin marketplace add /path/to/agent-plugins
/plugin install flutter-riverpod-guardrails@agent-plugins
```

Validate plugin manifests and hook definitions:

```bash
claude plugin validate ./plugins/flutter-riverpod-guardrails
```

## License

MIT — see [LICENSE](LICENSE).
