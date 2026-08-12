# study-loop (work in progress)

日本語版はこちら → [README.ja.md](README.ja.md)

> **⚠️ Not released.** This plugin lives under `dev/` on purpose: it is excluded from the marketplace, `/plugin install study-loop@agent-plugins` does not work, and commands, file formats, and behavior may change without notice. Everything below describes the current development snapshot.

Turns "I want to study X" into a loop instead of a wall of explanation: level diagnosis → generate an assignment file → the user fills in the answer → grade → feedback → next assignment. Topic-agnostic — programming, languages, math, history, exam prep, anything.

Main components:

- **`skills/study-loop/SKILL.md`** — the orchestration skill. Runs a 4-phase loop (setup → diagnostic → curriculum generation → lesson loop) and writes session state as Markdown under `.study/<topic-slug>/` (progress dashboard, curriculum, glossary, feedback rules, insights log).
- **Evidence-based design** — every design decision cites a meta-analysis or systematic review, documented with effect sizes and sources in `skills/study-loop/references/learning-science.md`. For example: feedback quality (Hattie & Timperley, *d* ≈ 0.70–1.00), retrieval practice / testing effect (Roediger & Karpicke, *d* ≈ 0.50–0.80), the self-explanation effect (Bisra et al., *g* ≈ 0.55), worked-examples fading (Sweller / Kalyuga, *d* ≈ 0.5–1.0), distributed practice / spacing (Cepeda et al., *d* ≈ 0.4–0.9), interleaved practice (Brunmair & Richter, *g* ≈ 0.42), and elaborative interrogation (Dunlosky et al., *d* ≈ 0.42).
- **Generator-Critic loop** — assignments are drafted by a Generator prompt and checked by a separate Critic pass before being shown to the user, to catch issues like answers leaked in comments.
- **`/study-ui`** — starts a local Flask web UI (`skills/study-loop/scripts/server.py`) bound to loopback only, for viewing lessons and filling in answers in the browser instead of editing Markdown directly, and opens it in your default browser automatically (use `--no-open` to skip). Optionally drives grading through a local Codex App Server session; `/study-ui-stop` shuts it down.

> **Note**: study-loop's skill instructions (`SKILL.md`) are currently written in Japanese, so the agent runs the loop most naturally in Japanese.

## Trying it from a clone

Load it into a Claude Code session without installing:

```bash
claude --plugin-dir ./dev/study-loop
```

## Running the Web UI standalone (without Claude Code)

The Web UI server does not depend on Claude Code at all — `start.sh`, `bootstrap.sh`, `stop.sh`, and `server.py` never reference `CLAUDE_PLUGIN_ROOT` or any other Claude Code environment variable, and `start.sh` builds its own Python virtualenv. From the repository root:

```bash
bash dev/study-loop/skills/study-loop/scripts/start.sh
```

On first run, `start.sh` calls `bootstrap.sh`, which creates a `.venv` next to the scripts and installs `flask`, `markdown`, and `pymdown-extensions` into it — no manual setup step needed.

`--backend` controls how the UI treats Codex (default `auto`):

- `auto` (default) — Codex is only started when you explicitly pick a start action in the UI (e.g. starting the diagnostic, grading an answer); loading the page or saving Markdown never launches it.
- `codex` — in the current implementation this behaves the same as `auto`; Codex is still only launched on demand from the UI, not on server startup.
- `manual` — Codex is never used. All grading goes through the Markdown-only manual flow (edit the answer file, then have Claude Code or another agent grade it).

If you plan to use Codex, the only prerequisite is having run `codex login` once beforehand — you do not need a Codex process already running. When a job needs Codex, `codex_app_server.py` starts `codex app-server --stdio` itself as a subprocess and checks authentication on connect; if you haven't logged in, the UI tells you to run `codex login` and falls back to the manual flow.

Other flags:

- `--port <n>` — Fixed port. Without it, `start.sh` searches ports 8765 through 8774 for a free one; with it, the script does not shift to another port on conflict.
- `--root <path>` — Path to the Study Loop session directory (default: `$PWD/.study`).
- `--host <addr>` — Bind address (default `127.0.0.1`). Only loopback addresses (`127.0.0.1`, `localhost`, `::1`) are accepted.
- `--no-open` — Don't automatically open a browser after starting (default: it opens one via `open`/`xdg-open`).

Stop the server with:

```bash
bash dev/study-loop/skills/study-loop/scripts/stop.sh
```
