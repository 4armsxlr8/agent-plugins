#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Flutter Riverpod Guardrails: Pre-Commit Lint Hook
#
# Intercepts `git commit` commands and runs `dart analyze` first.
# If analysis finds errors or warnings, the commit is blocked: the hook answers
# with a PreToolUse permissionDecision of "deny" and lists the offending lines
# in permissionDecisionReason, which is the field Claude actually reads.
# Anything this hook cannot make sense of (malformed input, no dart on PATH)
# lets the command through silently — a guardrail must never wedge the session.
#
# Triggered by: PreToolUse on Bash tool
# =============================================================================

# How many analyzer lines to quote back in the block reason.
MAX_LISTED=10

input=$(cat)

# Extract the command being run. Unparsable input: fail open.
command=$(jq -r '.tool_input.command // empty' <<<"$input" 2>/dev/null) || exit 0
[[ -z "$command" ]] && exit 0

# Only act on git commit commands. The commit may sit anywhere inside a
# compound command (`git add -A && git commit -m x`, `cd sub && git commit`)
# and git may carry its own flags first (`git -c user.name=x commit`), so match
# the `git ... commit` word pair wherever it appears instead of anchoring to
# the start of the line. The trailing boundary keeps `git commitfoo` out.
GIT_COMMIT_RE='(^|[^[:alnum:]_-])git([[:space:]]+-[^[:space:]]*([[:space:]]+[^-[:space:]][^[:space:]]*)?)*[[:space:]]+commit([^[:alnum:]_-]|$)'
if ! grep -qE "$GIT_COMMIT_RE" <<<"$command"; then
  exit 0
fi

# Check if we're in a Flutter/Dart project
if [[ ! -f "pubspec.yaml" ]]; then
  exit 0
fi

# Run dart analyze. `--no-fatal-warnings` keeps dart's own exit code out of the
# decision; the severity lines are counted here instead, which is what lets the
# hook block on warnings while ignoring the info-level lints that every real
# Flutter project carries by the dozen. No dart on PATH simply yields no
# matching lines, so the commit proceeds.
analyze_output=$(dart analyze --no-fatal-warnings 2>&1) || true

# Collect the error/warning lines.
# `grep -c` is deliberately avoided here: with zero matches it prints "0" AND
# exits 1, so a `|| echo "0"` fallback appended a second line and produced a
# two-line "count" that broke the arithmetic comparison below it.
issue_lines=$(grep -E '^[[:space:]]*(error|warning)[[:space:]]+' <<<"$analyze_output") || issue_lines=""

# Clean analysis, or info-level lints only: let the commit through silently.
[[ -z "$issue_lines" ]] && exit 0

issue_count=$(wc -l <<<"$issue_lines" | tr -d '[:space:]')

if [[ "$issue_count" -gt "$MAX_LISTED" ]]; then
  headline="dart analyze found ${issue_count} issue(s) (showing first ${MAX_LISTED} of ${issue_count}):"
else
  headline="dart analyze found ${issue_count} issue(s):"
fi

# Here string, not a pipe: `printf ... | head` makes the writer take a SIGPIPE
# as soon as head has its 10 lines, and under `set -o pipefail` that killed the
# hook outright (exit 141, no output) on large analyzer runs — which silently
# let the commit through, exactly the opposite of what this hook is for.
reason="${headline}"$'\n'
reason+="$(head -n "$MAX_LISTED" <<<"$issue_lines")"$'\n'
reason+=$'\n'"Fix these issues before committing."

jq -n --arg reason "$reason" --arg count "$issue_count" '{
  systemMessage: ("Commit blocked: dart analyze found " + $count + " issue(s)."),
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: $reason
  }
}'
