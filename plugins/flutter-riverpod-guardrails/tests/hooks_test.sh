#!/usr/bin/env bash
# =============================================================================
# Tests for the flutter-riverpod-guardrails hook scripts.
#
# Plain bash + jq only (no bats or other external test framework).
# The suite is self-contained: it builds every fixture it needs inside a
# temporary directory at start-up and removes that directory on exit. Tests
# share no mutable state (each one gets its own stdin, stdout/stderr capture
# files and dart trace file), so they can run in any order.
#
# Usage: ./tests/hooks_test.sh
# Exits 0 when every assertion passes, 1 otherwise.
# =============================================================================

# NOTE: `set -e` is deliberately NOT used. A failing assertion must be recorded
# and reported, not abort the whole run.
set -uo pipefail

TEST_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PLUGIN_ROOT=$(cd "$TEST_DIR/.." && pwd)
CHECK_ARCH="$PLUGIN_ROOT/scripts/check-architecture.sh"
PRE_COMMIT="$PLUGIN_ROOT/scripts/pre-commit-lint.sh"
HOOKS_JSON="$PLUGIN_ROOT/hooks/hooks.json"

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required to run these tests." >&2
  exit 1
fi
for required in "$CHECK_ARCH" "$PRE_COMMIT" "$HOOKS_JSON"; do
  if [[ ! -f "$required" ]]; then
    echo "file not found: $required" >&2
    exit 1
  fi
done

# ---------------------------------------------------------------------------
# Result bookkeeping
# ---------------------------------------------------------------------------
PASS_COUNT=0
FAIL_COUNT=0
FAILED_LIST=""

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  printf 'PASS  %s\n' "$1"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  FAILED_LIST="${FAILED_LIST}  - $1"$'\n'
  printf 'FAIL  %s\n        %s\n' "$1" "$2"
}

# Keeps failure output readable when the value under test is huge.
excerpt() {
  printf '%s' "$1" | head -c 400 | head -5 | tr '\n' '|'
}

assert_rc() { # name expected actual
  if [[ "$2" == "$3" ]]; then
    pass "$1"
  else
    fail "$1" "expected exit code $2, got $3"
  fi
}

assert_empty() { # name value label
  if [[ -z "$2" ]]; then
    pass "$1"
  else
    fail "$1" "expected empty ${3:-value}, got: $(excerpt "$2")"
  fi
}

assert_nonempty() { # name value
  if [[ -n "$2" ]]; then
    pass "$1"
  else
    fail "$1" "expected a non-empty value, got nothing"
  fi
}

assert_contains() { # name haystack needle
  case "$2" in
    *"$3"*) pass "$1" ;;
    *) fail "$1" "expected to contain [$3], got: $(excerpt "$2")" ;;
  esac
}

assert_not_contains() { # name haystack needle
  case "$2" in
    *"$3"*) fail "$1" "expected NOT to contain [$3], got: $(excerpt "$2")" ;;
    *) pass "$1" ;;
  esac
}

# Reads a jq path out of a JSON string. Prints the value, returns non-zero when
# the JSON is invalid or the path is missing/null.
json_get() { # json path
  printf '%s' "$1" | jq -er "$2" 2>/dev/null
}

assert_json_eq() { # name json path expected
  local actual
  actual=$(json_get "$2" "$3")
  if [[ $? -ne 0 ]]; then
    fail "$1" "jq path $3 is missing or null; raw output: $(excerpt "$2")"
    return
  fi
  if [[ "$actual" == "$4" ]]; then
    pass "$1"
  else
    fail "$1" "expected $3 == [$4], got [$actual]"
  fi
}

assert_json_contains() { # name json path needle
  local actual
  actual=$(json_get "$2" "$3")
  if [[ $? -ne 0 ]]; then
    fail "$1" "jq path $3 is missing or null; raw output: $(excerpt "$2")"
    return
  fi
  assert_contains "$1" "$actual" "$4"
}

assert_json_not_contains() { # name json path needle
  local actual
  actual=$(json_get "$2" "$3")
  if [[ $? -ne 0 ]]; then
    fail "$1" "jq path $3 is missing or null; raw output: $(excerpt "$2")"
    return
  fi
  assert_not_contains "$1" "$actual" "$4"
}

assert_json_nonempty() { # name json path
  local actual
  actual=$(json_get "$2" "$3")
  if [[ $? -ne 0 ]]; then
    fail "$1" "jq path $3 is missing or null; raw output: $(excerpt "$2")"
    return
  fi
  assert_nonempty "$1" "$actual"
}

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
TMP=$(mktemp -d "${TMPDIR:-/tmp}/guardrails_hooks_test.XXXXXX") || exit 1
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

# The architecture checker derives the layer from the path, so the temporary
# directory itself must not look like a layer directory.
case "$TMP" in
  */domain/* | */data/* | */application/* | */presentation/*)
    echo "temporary directory $TMP collides with a layer name; aborting." >&2
    exit 1
    ;;
esac

FX="$TMP/fx"
OUTDIR="$TMP/out"
mkdir -p "$OUTDIR" "$FX/bin"

# PATH used by the "dart is not installed" test. Must carry the tools the hook
# itself needs (jq, grep, head, wc, tr) but not dart.
NO_DART_PATH="/usr/bin:/bin:/usr/sbin:/sbin"
if PATH="$NO_DART_PATH" command -v dart >/dev/null 2>&1; then
  echo "dart is reachable through $NO_DART_PATH; the missing-dart test cannot run." >&2
  exit 1
fi

HOOK_LIB="$FX/hook/lib"
mkdir -p \
  "$HOOK_LIB/features/x/domain" \
  "$HOOK_LIB/features/x/data" \
  "$HOOK_LIB/features/x/application" \
  "$HOOK_LIB/features/x/presentation" \
  "$HOOK_LIB/app/providers"

cat >"$HOOK_LIB/features/x/domain/entity.dart" <<'DART'
import 'package:flutter/material.dart';

class Entity {
  const Entity({required this.id});
  final String id;
}
DART

cat >"$HOOK_LIB/features/x/domain/clean_entity.dart" <<'DART'
class CleanEntity {
  const CleanEntity({required this.id});
  final String id;
}
DART

# Generated file: violating on purpose, but must be skipped.
cat >"$HOOK_LIB/features/x/domain/model.freezed.dart" <<'DART'
import 'package:flutter/material.dart';

class _$Model {}
DART

cat >"$HOOK_LIB/features/x/data/repo.dart" <<'DART'
class RemoteRepo {
  String baseUrl() {
    return kIsWeb ? 'https://web.example' : 'https://api.example';
  }
}
DART

cat >"$HOOK_LIB/features/x/application/provider.dart" <<'DART'
import 'package:flutter/material.dart';

final counterProvider = StateProvider<int>((ref) => 0);
DART

# `Widget _buildHeader() {` sits on line 11 of this file; test 4 asserts that
# exact line number shows up in the reported violation.
cat >"$HOOK_LIB/features/x/presentation/screen.dart" <<'DART'
import 'package:flutter/material.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(children: [_buildHeader()]);
  }

  Widget _buildHeader() {
    return const Text('header');
  }
}
DART

# Outside every known layer directory: must be ignored.
cat >"$HOOK_LIB/app/providers/x.dart" <<'DART'
import 'package:flutter/material.dart';

final appProvider = Provider<int>((ref) => 0);
DART

# 60 function-style widgets => 60 violations. Widget i opens on line
# 4 + (i - 1) * 3, so #1 is line 4, #50 is line 151 and #51 is line 154.
BIG_SCREEN="$HOOK_LIB/features/x/presentation/screen_big.dart"
{
  echo "import 'package:flutter/material.dart';"
  echo ""
  echo "class BigScreen extends StatelessWidget {"
  i=1
  while [[ $i -le 60 ]]; do
    echo "  Widget _buildW${i}() {"
    echo "    return const Text('${i}');"
    echo "  }"
    i=$((i + 1))
  done
  echo "}"
} >"$BIG_SCREEN"

# --- scan mode trees -------------------------------------------------------
SCAN_DIRTY="$FX/scan_dirty/lib"
mkdir -p "$SCAN_DIRTY/features/x/domain" "$SCAN_DIRTY/features/x/data"

cat >"$SCAN_DIRTY/features/x/domain/bad_entity.dart" <<'DART'
import 'package:flutter/material.dart';

class BadEntity {}
DART

cat >"$SCAN_DIRTY/features/x/domain/ok_entity.dart" <<'DART'
class OkEntity {
  const OkEntity();
}
DART

cat >"$SCAN_DIRTY/features/x/data/bad_repo.dart" <<'DART'
class BadRepo {
  String host() => kIsWeb ? 'web' : 'native';
}
DART

SCAN_CLEAN="$FX/scan_clean/lib"
mkdir -p "$SCAN_CLEAN/features/x/domain" "$SCAN_CLEAN/features/x/presentation"

cat >"$SCAN_CLEAN/features/x/domain/ok_entity.dart" <<'DART'
class OkEntity {
  const OkEntity();
}
DART

cat >"$SCAN_CLEAN/features/x/presentation/ok_screen.dart" <<'DART'
import 'package:flutter/material.dart';

class OkScreen extends StatelessWidget {
  const OkScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const Text('ok');
  }
}
DART

# --- pre-commit fixtures ---------------------------------------------------
mkdir -p "$FX/proj" "$FX/nopubspec"
cat >"$FX/proj/pubspec.yaml" <<'YAML'
name: myapp
environment:
  sdk: ">=3.0.0 <4.0.0"
YAML

# Fake `dart` placed at the front of PATH. FAKE_DART_MODE picks the output and
# FAKE_DART_TRACE records that it was invoked at all.
#
# The real `dart analyze` right-justifies the severity in a 7-character column,
# so the lines read "  error - ...", "warning - ..." and "   info - ...".
# Exit codes mirror the real tool under --no-fatal-warnings: errors make it
# non-zero, an info-only run stays at 0.
cat >"$FX/bin/dart" <<'FAKEDART'
#!/usr/bin/env bash
if [[ -n "${FAKE_DART_TRACE:-}" ]]; then
  printf 'dart %s\n' "$*" >>"$FAKE_DART_TRACE"
fi

case "${FAKE_DART_MODE:-clean}" in
  dirty)
    printf '%s\n' \
      'Analyzing myapp...' \
      '' \
      "  error - lib/main.dart:3:1 - Undefined name 'foo'. - undefined_identifier" \
      'warning - lib/util.dart:10:5 - Unused import. - unused_import' \
      '   info - lib/style.dart:7:3 - Prefer const with constant constructors. - prefer_const_constructors' \
      '' \
      '3 issues found.'
    exit 3
    ;;
  info)
    printf '%s\n' \
      'Analyzing myapp...' \
      '' \
      '   info - lib/style.dart:7:3 - Prefer const with constant constructors. - prefer_const_constructors' \
      '   info - lib/style.dart:9:3 - Use key in widget constructors. - use_key_in_widget_constructors' \
      '   info - lib/home.dart:2:1 - Sort directive sections alphabetically. - directives_ordering' \
      '' \
      '3 issues found.'
    exit 0
    ;;
  flood)
    printf '%s\n' 'Analyzing myapp...' ''
    i=1
    while [[ $i -le 600 ]]; do
      printf "  error - lib/generated/module_%s/very_long_generated_widget_file_%s.dart:%s:13 - Undefined name 'someMissingIdentifier%s'. - undefined_identifier\n" \
        "$i" "$i" "$i" "$i"
      i=$((i + 1))
    done
    printf '%s\n' \
      '   info - lib/style.dart:7:3 - Prefer const with constant constructors. - prefer_const_constructors' \
      '' \
      '601 issues found.'
    exit 3
    ;;
  *)
    printf '%s\n' 'Analyzing myapp...' '' 'No issues found!'
    exit 0
    ;;
esac
FAKEDART
chmod +x "$FX/bin/dart"

# ---------------------------------------------------------------------------
# Runners. Each fills OUT / ERR / RC (and TRACE for the pre-commit hook).
# ---------------------------------------------------------------------------
OUT=""
ERR=""
RC=0
TRACE=""

run_check_hook() { # slug json_stdin
  local slug="$1" input="$2"
  local o="$OUTDIR/$slug.out" e="$OUTDIR/$slug.err"
  printf '%s' "$input" | bash "$CHECK_ARCH" >"$o" 2>"$e"
  RC=$?
  OUT=$(cat "$o")
  ERR=$(cat "$e")
}

run_check_scan() { # slug lib_dir
  local slug="$1" dir="$2"
  local o="$OUTDIR/$slug.out" e="$OUTDIR/$slug.err"
  bash "$CHECK_ARCH" --scan "$dir" >"$o" 2>"$e"
  RC=$?
  OUT=$(cat "$o")
  ERR=$(cat "$e")
}

run_pre_commit() { # slug workdir fake_dart_mode json_stdin [path_override]
  local slug="$1" workdir="$2" mode="$3" input="$4"
  local path_value="${5:-$FX/bin:$PATH}"
  local o="$OUTDIR/$slug.out" e="$OUTDIR/$slug.err" t="$OUTDIR/$slug.trace"
  rm -f "$t"
  printf '%s' "$input" | (
    cd "$workdir" || exit 99
    PATH="$path_value" FAKE_DART_MODE="$mode" FAKE_DART_TRACE="$t" \
      bash "$PRE_COMMIT"
  ) >"$o" 2>"$e"
  RC=$?
  OUT=$(cat "$o")
  ERR=$(cat "$e")
  TRACE=""
  [[ -f "$t" ]] && TRACE=$(cat "$t")
}

post_tool_use_input() { # file_path
  jq -n --arg fp "$1" '{tool_name: "Write", tool_input: {file_path: $fp}}'
}

pre_tool_use_input() { # command
  jq -n --arg cmd "$1" '{tool_name: "Bash", tool_input: {command: $cmd}}'
}

# Shorthand for the many "this command must be blocked" cases.
expect_commit_blocked() { # slug label command
  run_pre_commit "$1" "$FX/proj" "dirty" "$(pre_tool_use_input "$3")"
  assert_rc      "$2 exits 0" 0 "$RC"
  assert_json_eq "$2 is denied" "$OUT" '.hookSpecificOutput.permissionDecision' 'deny'
  assert_empty   "$2 writes nothing to stderr" "$ERR" "stderr"
}

expect_commit_ignored() { # slug label command
  run_pre_commit "$1" "$FX/proj" "dirty" "$(pre_tool_use_input "$3")"
  assert_rc    "$2 exits 0" 0 "$RC"
  assert_empty "$2 writes nothing to stdout" "$OUT" "stdout"
  assert_empty "$2 writes nothing to stderr" "$ERR" "stderr"
  assert_empty "$2 never invokes dart" "$TRACE" "dart trace"
}

# ===========================================================================
# Seam 1: check-architecture.sh hook mode
# ===========================================================================
echo "--- seam 1: check-architecture.sh (hook mode) ---"

# 1. Domain layer violation
run_check_hook "t01" "$(post_tool_use_input "$HOOK_LIB/features/x/domain/entity.dart")"
assert_rc          "T01 domain violation exits 0" 0 "$RC"
assert_json_eq     "T01 hookEventName is PostToolUse" "$OUT" '.hookSpecificOutput.hookEventName' 'PostToolUse'
assert_json_contains "T01 additionalContext names the Domain layer" "$OUT" '.hookSpecificOutput.additionalContext' 'Domain'
assert_json_nonempty "T01 systemMessage is non-empty" "$OUT" '.systemMessage'
assert_empty       "T01 writes nothing to stderr" "$ERR" "stderr"

# 2. Data layer violation
run_check_hook "t02" "$(post_tool_use_input "$HOOK_LIB/features/x/data/repo.dart")"
assert_rc          "T02 data violation exits 0" 0 "$RC"
assert_json_eq     "T02 hookEventName is PostToolUse" "$OUT" '.hookSpecificOutput.hookEventName' 'PostToolUse'
assert_json_contains "T02 additionalContext names the Data layer" "$OUT" '.hookSpecificOutput.additionalContext' 'Data'
assert_json_contains "T02 additionalContext mentions kIsWeb" "$OUT" '.hookSpecificOutput.additionalContext' 'kIsWeb'
assert_json_nonempty "T02 systemMessage is non-empty" "$OUT" '.systemMessage'
assert_empty       "T02 writes nothing to stderr" "$ERR" "stderr"

# 3. Application layer violation
run_check_hook "t03" "$(post_tool_use_input "$HOOK_LIB/features/x/application/provider.dart")"
assert_rc          "T03 application violation exits 0" 0 "$RC"
assert_json_eq     "T03 hookEventName is PostToolUse" "$OUT" '.hookSpecificOutput.hookEventName' 'PostToolUse'
assert_json_contains "T03 additionalContext names the Application layer" "$OUT" '.hookSpecificOutput.additionalContext' 'Application'
assert_json_nonempty "T03 systemMessage is non-empty" "$OUT" '.systemMessage'
assert_empty       "T03 writes nothing to stderr" "$ERR" "stderr"

# 4. Presentation layer violation (function-style widget), with line number
run_check_hook "t04" "$(post_tool_use_input "$HOOK_LIB/features/x/presentation/screen.dart")"
assert_rc          "T04 presentation violation exits 0" 0 "$RC"
assert_json_eq     "T04 hookEventName is PostToolUse" "$OUT" '.hookSpecificOutput.hookEventName' 'PostToolUse'
assert_json_contains "T04 additionalContext names the Presentation layer" "$OUT" '.hookSpecificOutput.additionalContext' 'Presentation'
assert_json_contains "T04 additionalContext carries the line number" "$OUT" '.hookSpecificOutput.additionalContext' 'screen.dart:11]'
assert_json_nonempty "T04 systemMessage is non-empty" "$OUT" '.systemMessage'
assert_empty       "T04 writes nothing to stderr" "$ERR" "stderr"

# 5. Clean domain file: silent
run_check_hook "t05" "$(post_tool_use_input "$HOOK_LIB/features/x/domain/clean_entity.dart")"
assert_rc    "T05 clean domain file exits 0" 0 "$RC"
assert_empty "T05 clean domain file writes nothing to stdout" "$OUT" "stdout"
assert_empty "T05 clean domain file writes nothing to stderr" "$ERR" "stderr"

# 6. Generated *.freezed.dart file: skipped even though it violates
run_check_hook "t06" "$(post_tool_use_input "$HOOK_LIB/features/x/domain/model.freezed.dart")"
assert_rc    "T06 freezed file exits 0" 0 "$RC"
assert_empty "T06 freezed file writes nothing to stdout" "$OUT" "stdout"
assert_empty "T06 freezed file writes nothing to stderr" "$ERR" "stderr"

# 7. Path outside every layer directory: ignored
run_check_hook "t07" "$(post_tool_use_input "$HOOK_LIB/app/providers/x.dart")"
assert_rc    "T07 non-layer path exits 0" 0 "$RC"
assert_empty "T07 non-layer path writes nothing to stdout" "$OUT" "stdout"
assert_empty "T07 non-layer path writes nothing to stderr" "$ERR" "stderr"

# 8. Payload without file_path
run_check_hook "t08" "$(jq -n '{tool_name: "Write", tool_input: {}}')"
assert_rc    "T08 missing file_path exits 0" 0 "$RC"
assert_empty "T08 missing file_path writes nothing to stdout" "$OUT" "stdout"
assert_empty "T08 missing file_path writes nothing to stderr" "$ERR" "stderr"

# ===========================================================================
# Seam 2: check-architecture.sh --scan mode (regression only)
# ===========================================================================
echo "--- seam 2: check-architecture.sh (--scan mode) ---"

# 9. Tree holding exactly two violations
run_check_scan "t09" "$SCAN_DIRTY"
assert_rc       "T09 dirty scan exits 1" 1 "$RC"
assert_contains "T09 dirty scan reports 2 violations" "$OUT" "2 violations"

# 10. Clean tree
run_check_scan "t10" "$SCAN_CLEAN"
assert_rc       "T10 clean scan exits 0" 0 "$RC"
assert_contains "T10 clean scan reports success" "$OUT" "All clean architecture rules satisfied."

# ===========================================================================
# Seam 3: pre-commit-lint.sh
# ===========================================================================
echo "--- seam 3: pre-commit-lint.sh ---"

# 11. git commit with analyzer issues: blocked
run_pre_commit "t11" "$FX/proj" "dirty" "$(pre_tool_use_input 'git commit -m "x"')"
assert_rc          "T11 blocking commit still exits 0" 0 "$RC"
assert_json_eq     "T11 hookEventName is PreToolUse" "$OUT" '.hookSpecificOutput.hookEventName' 'PreToolUse'
assert_json_eq     "T11 permissionDecision is deny" "$OUT" '.hookSpecificOutput.permissionDecision' 'deny'
assert_json_contains "T11 reason states the issue count" "$OUT" '.hookSpecificOutput.permissionDecisionReason' '2 issue'
assert_json_contains "T11 reason quotes the analyzer error line" "$OUT" '.hookSpecificOutput.permissionDecisionReason' "error - lib/main.dart:3:1"
assert_json_contains "T11 reason quotes the analyzer warning line" "$OUT" '.hookSpecificOutput.permissionDecisionReason' "warning - lib/util.dart:10:5"
assert_json_not_contains "T11 reason ignores info lines" "$OUT" '.hookSpecificOutput.permissionDecisionReason' "info - lib/style.dart"
assert_json_nonempty "T11 systemMessage is non-empty" "$OUT" '.systemMessage'
assert_empty       "T11 writes nothing to stderr" "$ERR" "stderr"

# 12. git commit with a clean analyzer run: silent
run_pre_commit "t12" "$FX/proj" "clean" "$(pre_tool_use_input 'git commit -m "x"')"
assert_rc    "T12 clean analyze exits 0" 0 "$RC"
assert_empty "T12 clean analyze writes nothing to stdout" "$OUT" "stdout"
assert_empty "T12 clean analyze writes nothing to stderr" "$ERR" "stderr"

# 13. Non-commit command: untouched, and dart must never run
run_pre_commit "t13" "$FX/proj" "dirty" "$(pre_tool_use_input 'ls -la')"
assert_rc    "T13 non-commit command exits 0" 0 "$RC"
assert_empty "T13 non-commit command writes nothing to stdout" "$OUT" "stdout"
assert_empty "T13 non-commit command writes nothing to stderr" "$ERR" "stderr"
assert_empty "T13 non-commit command never invokes dart" "$TRACE" "dart trace"

# 14. git commit outside a Dart project
run_pre_commit "t14" "$FX/nopubspec" "dirty" "$(pre_tool_use_input 'git commit -m "x"')"
assert_rc    "T14 commit without pubspec.yaml exits 0" 0 "$RC"
assert_empty "T14 commit without pubspec.yaml writes nothing to stdout" "$OUT" "stdout"
assert_empty "T14 commit without pubspec.yaml writes nothing to stderr" "$ERR" "stderr"

# 15. Very large analyzer output must not kill the hook via SIGPIPE
run_pre_commit "t15" "$FX/proj" "flood" "$(pre_tool_use_input 'git commit -m "x"')"
assert_rc          "T15 huge analyzer output still exits 0" 0 "$RC"
assert_json_eq     "T15 huge analyzer output is denied" "$OUT" '.hookSpecificOutput.permissionDecision' 'deny'
assert_json_contains "T15 reason states the total issue count" "$OUT" '.hookSpecificOutput.permissionDecisionReason' '600 issue'
assert_json_contains "T15 reason says how many lines it shows" "$OUT" '.hookSpecificOutput.permissionDecisionReason' 'showing first 10 of 600'
assert_json_contains "T15 reason quotes the first issue" "$OUT" '.hookSpecificOutput.permissionDecisionReason' 'module_1/'
assert_json_not_contains "T15 reason stops after 10 issues" "$OUT" '.hookSpecificOutput.permissionDecisionReason' 'module_11/'
assert_empty       "T15 huge analyzer output writes nothing to stderr" "$ERR" "stderr"

# 16. Info-only analysis (the normal state of a real Flutter project): no block
run_pre_commit "t16" "$FX/proj" "info" "$(pre_tool_use_input 'git commit -m "x"')"
assert_rc    "T16 info-only analyze exits 0" 0 "$RC"
assert_empty "T16 info-only analyze writes nothing to stdout" "$OUT" "stdout"
assert_empty "T16 info-only analyze writes nothing to stderr" "$ERR" "stderr"

# 17-19. Compound and flag-carrying commit commands must still be caught
expect_commit_blocked "t17" "T17 chained git commit" 'git add -A && git commit -m x'
expect_commit_blocked "t18" "T18 git commit behind -c flags" 'git -c user.name=x commit -m y'
expect_commit_blocked "t19" "T19 git commit after cd" 'cd sub && git commit -m z'

# 20-21. Nearby commands that are not a commit
expect_commit_ignored "t20" "T20 git log" 'git log --oneline'
expect_commit_ignored "t21" "T21 git commitfoo" 'git commitfoo --help'

# 22. Malformed stdin: fail open, silently
run_pre_commit "t22" "$FX/proj" "dirty" 'not json at all {'
assert_rc    "T22 pre-commit fails open on invalid JSON" 0 "$RC"
assert_empty "T22 pre-commit invalid JSON writes nothing to stdout" "$OUT" "stdout"
assert_empty "T22 pre-commit invalid JSON writes nothing to stderr" "$ERR" "stderr"

# 23. dart missing from PATH: fail open, silently
run_pre_commit "t23" "$FX/proj" "dirty" "$(pre_tool_use_input 'git commit -m "x"')" "$NO_DART_PATH"
assert_rc    "T23 missing dart fails open" 0 "$RC"
assert_empty "T23 missing dart writes nothing to stdout" "$OUT" "stdout"
assert_empty "T23 missing dart writes nothing to stderr" "$ERR" "stderr"

# ===========================================================================
# Seam 4: shared robustness / output-size guards
# ===========================================================================
echo "--- seam 4: robustness ---"

# 24. Malformed stdin for the architecture hook: fail open, silently
run_check_hook "t24" 'not json at all {'
assert_rc    "T24 check-architecture fails open on invalid JSON" 0 "$RC"
assert_empty "T24 check-architecture invalid JSON writes nothing to stdout" "$OUT" "stdout"
assert_empty "T24 check-architecture invalid JSON writes nothing to stderr" "$ERR" "stderr"

# 25. A file with 60 violations must be truncated to the first 50
run_check_hook "t25" "$(post_tool_use_input "$BIG_SCREEN")"
assert_rc          "T25 many violations exits 0" 0 "$RC"
assert_json_contains "T25 additionalContext keeps the first violation" "$OUT" '.hookSpecificOutput.additionalContext' 'screen_big.dart:4]'
assert_json_contains "T25 additionalContext keeps the 50th violation" "$OUT" '.hookSpecificOutput.additionalContext' 'screen_big.dart:151]'
assert_json_not_contains "T25 additionalContext drops the 51st violation" "$OUT" '.hookSpecificOutput.additionalContext' 'screen_big.dart:154]'
assert_json_contains "T25 additionalContext reports the truncation" "$OUT" '.hookSpecificOutput.additionalContext' '... and 10 more violations (60 total)'
assert_json_contains "T25 systemMessage reports the truncation" "$OUT" '.systemMessage' '... and 10 more violations (60 total)'
assert_empty       "T25 many violations writes nothing to stderr" "$ERR" "stderr"

# 26. hooks.json must allow a cold `dart analyze` to finish
PRE_TIMEOUT=$(jq -r '.hooks.PreToolUse[0].hooks[0].timeout' "$HOOKS_JSON" 2>/dev/null)
assert_rc "T26 PreToolUse hook timeout is 120s" "120" "$PRE_TIMEOUT"

# ===========================================================================
# Summary
# ===========================================================================
echo ""
echo "========================================="
printf 'Assertions: %d passed, %d failed\n' "$PASS_COUNT" "$FAIL_COUNT"
if [[ "$FAIL_COUNT" -gt 0 ]]; then
  echo ""
  echo "Failed assertions:"
  printf '%s' "$FAILED_LIST"
  exit 1
fi
echo "All assertions passed."
exit 0
