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
- **`skills/plan-evaluator`** — audits the plan `find-unknowns` writes — premises, acceptance criteria, self-containedness — in an isolated context before it reaches the implementation session.
- **`skills/plan-implement`** — drives implementation and the mechanical/behavioral/exception gates through to the commit handoff.
- **`skills/test-generator`** / **`skills/code-generator`** — the red and green sides of TDD, run as separate subagents so the same agent can't write both a test and the code that games it.
- **`skills/diff-review`** — an "exception viewer" that surfaces only risky hunks once behavior is confirmed, instead of asking a human to read every line.
- **`skills/html-report`** — turns long prose reports into a self-contained HTML page.
- **`skills/plan-commit`** — folds the finished plan into the commit message and deletes the plan file.
- **`skills/tdd`** — a reference for what makes a test worth keeping, forked from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT).

Plans and reports are written to `docs/crystallize/plans/` and `docs/crystallize/reports/` in the target repository.

### ui-craft — UI/UX design knowledge, translated for an agent that can't see

Translates UI/UX essentials — the judgment calls a designer carries as experience, like "this is subtly beautiful" or "this is subtly off" — into a form an agent that cannot actually look at the screen can execute: a starting numeric value, a token-based way to write it down, and a screenshot-based verification step. Meant to grow over time; currently ships one skill, `visual-adjustment`.

Main components:

- **`skills/visual-adjustment/SKILL.md`** — seven optical-adjustment patterns (optical vertical centering, color area effect, centroid alignment for asymmetric shapes, apparent size by shape, overshoot, density vs. centroid, Hermann grid), each with a starting value, a token-based way to write the correction, and a caveat about double-correcting already-adjusted assets. Fires on "optical correction" / "visual adjustment," and also whenever a mock or UI implementation is about to "align" spacing, color, or icon placement to a uniform value.
- **`skills/visual-adjustment/references/sources.md`** — the source for each number the skill uses (a Speaker Deck by Yuichi Hara of CyberAgent/Ameba, Bjango's optical-adjustment formulas, Material Design's icon keylines, and others), tagged by whether the value is sourced, derived geometrically, or a placeholder heuristic.

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
