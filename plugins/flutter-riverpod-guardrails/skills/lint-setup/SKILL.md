---
name: lint-setup
description: Set up import_lint and riverpod_lint to enforce the layered architecture in a Flutter + Riverpod project. Use when adding lint enforcement of layer boundaries.
metadata:
  purpose: produce
  trigger: user
  shape: atomic
---

# Lint Enforcement of Layer Boundaries

Adds `import_lint` and `riverpod_lint` to a Flutter project so that the four-layer
dependency direction is enforced by `dart analyze`, not only by this plugin's hooks.

## Setup

1. **Install the import_lint CLI.**

   ```bash
   flutter pub add --dev import_lint
   ```

   This is not what makes the analyzer plugin work — that comes from step 2. It is
   only so `dart run import_lint` is available, which honours the top-level
   `severity: "error"` key and exits 1 on a violation.

2. **Never `pub add` riverpod_lint.** Declare it in `analysis_options.yaml` under
   `plugins:` only. Adding it to the pubspec cannot resolve — flutter_riverpod 3.x
   pulls in riverpod, whose `test ^1.0.0` conflicts with the `test_api` the SDK's
   flutter_test pins (`flutter_test from sdk is incompatible with riverpod_lint
   >=3.1.6`). `plugins:` entries are resolved in a separate pub solve under
   `~/.dartServer/.plugin_manager/`, so they work without being in the pubspec.

3. **Apply the template** from `references/analysis-options-template.md` to
   `analysis_options.yaml`, then replace every `<package_name>` with the `name:`
   value from `pubspec.yaml`. If you skip this replacement the import_lint `target`
   globs match nothing and every rule silently passes.

4. **Run `dart analyze`.** The first run can be slow while the plugins compile.

5. **Verify the rules actually fire.** Add `import 'package:flutter/material.dart';`
   to any file under a `domain/` directory, run `dart analyze`, and confirm it
   reports an `error` and exits non-zero. Then remove the import. Without this
   check you cannot tell a working setup apart from one that reports nothing.

## Gotchas

- **By default every plugin violation is reported at `info`, and `dart analyze`
  exits 0.** Neither CI nor this plugin's pre-commit hook stops anything. This is
  the most dangerous failure mode because the setup looks complete.
- **The only working way to raise severity is `plugins: <name>: diagnostics:
  <code>: error|warning`.** The template does this for every rule.
- **Enabling any analyzer plugin makes the analyzer's own diagnostics appear
  twice.** The duplication is per-run, not per-plugin. Counts are inflated; nothing
  is hidden.

Four things look right and are not (all measured 2026-08). The reasons are in
`references/analysis-options-template.md`:

- `analyzer: errors: import_lint: error` — rejected as an unrecognized code, even
  though the import_lint README recommends it.
- A wildcard `"*": warning` under `diagnostics:` — silently ignored, so all 15
  riverpod_lint rules must be listed one by one.
- The top-level `import_lint: severity:` key — affects only the
  `dart run import_lint` CLI, never `dart analyze`.
- `riverpod_lint` pinned any higher than `^3.1.4` — breaks the shared plugin solve.

## How Lint and the Hooks Divide the Work

**They overlap on the layer imports, deliberately.** `check-architecture.sh` still
greps the same import lines import_lint now checks, because the two land at
different moments: the PostToolUse hook answers within the edit that caused the
violation, so Claude is told immediately, while lint is the version of record for
the IDE, CI, and the commit gate. Reporting a violation twice costs nothing.

Only lint catches **relative** imports (`../data/foo.dart`), which it resolves to a
`package:` URI before matching; the hook greps the literal import line. Only the
hooks cover the rules that are not import edges: `kIsWeb` and `BuildContext` in
data, `Navigator` / `showDialog` / `ScaffoldMessenger` in application,
`abstract class` in data, and function-style widgets in presentation.

The pre-commit hook counts `error` and `warning` lines in `dart analyze` output, so
once severities are raised it denies commits with layer violations too (verified).
