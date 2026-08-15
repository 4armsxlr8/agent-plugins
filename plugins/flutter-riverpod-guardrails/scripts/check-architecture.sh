#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Flutter Riverpod Clean Architecture Compliance Checker
#
# Each layer has strict dependency rules:
#   Domain       -> No external dependencies (pure Dart only)
#   Data         -> Domain only (no Flutter, no Riverpod)
#   Application  -> Domain + Data (flutter_riverpod allowed, no Flutter UI)
#   Presentation -> Application + Domain (no direct Data access)
#
# Usage:
#   Hook mode:  Called automatically via Claude Code PostToolUse hook
#   Scan mode:  ./check-architecture.sh --scan <lib_directory>
# =============================================================================

VIOLATIONS=()

# How many violations to list in the hook feedback. A single generated file can
# produce hundreds of hits, and dumping all of them floods Claude's context.
MAX_LISTED_VIOLATIONS=50

# ---------------------------------------------------------------------------
# Pattern checker
# ---------------------------------------------------------------------------
check_pattern() {
  local file="$1" pattern="$2" message="$3"
  if grep -qE "$pattern" "$file" 2>/dev/null; then
    VIOLATIONS+=("$message")
  fi
}

# ---------------------------------------------------------------------------
# Layer-specific checks for a single file
# ---------------------------------------------------------------------------
check_file() {
  local file_path="$1"
  local display_name="${2:-$(basename "$file_path")}"

  # Guard: only .dart, skip generated, skip missing
  [[ "$file_path" != *.dart ]]          && return 0
  [[ "$file_path" == *.freezed.dart ]]  && return 0
  [[ "$file_path" == *.g.dart ]]        && return 0
  [[ ! -f "$file_path" ]]              && return 0

  # Determine layer
  local layer=""
  case "$file_path" in
    */domain/*)       layer="domain" ;;
    */data/*)         layer="data" ;;
    */application/*)  layer="application" ;;
    */presentation/*) layer="presentation" ;;
    *) return 0 ;;
  esac

  # --- Domain Layer: pure Dart only -------------------------------------------
  if [[ "$layer" == "domain" ]]; then
    check_pattern "$file_path" "^import.*package:flutter/" \
      "[${display_name}] Domain: package:flutter/ import prohibited"
    check_pattern "$file_path" "^import.*package:flutter_riverpod/" \
      "[${display_name}] Domain: flutter_riverpod import prohibited"
    check_pattern "$file_path" "^import.*package:riverpod" \
      "[${display_name}] Domain: riverpod import prohibited"
    check_pattern "$file_path" "^import.*package:cloud_firestore/" \
      "[${display_name}] Domain: cloud_firestore import prohibited"
    check_pattern "$file_path" "^import.*package:firebase_" \
      "[${display_name}] Domain: firebase package import prohibited"
    check_pattern "$file_path" "^import.*package:http/" \
      "[${display_name}] Domain: http package import prohibited"
    check_pattern "$file_path" "^import.*package:dio/" \
      "[${display_name}] Domain: dio package import prohibited"
  fi

  # --- Data Layer: no Flutter, no Riverpod, no platform constants -------------
  if [[ "$layer" == "data" ]]; then
    check_pattern "$file_path" "^import.*package:flutter/" \
      "[${display_name}] Data: package:flutter/ import prohibited"
    check_pattern "$file_path" "^import.*package:flutter_riverpod/" \
      "[${display_name}] Data: flutter_riverpod import prohibited"
    check_pattern "$file_path" "^import.*package:riverpod" \
      "[${display_name}] Data: riverpod import prohibited"
    check_pattern "$file_path" "\bkIsWeb\b" \
      "[${display_name}] Data: kIsWeb direct use prohibited (inject via constructor)"
    check_pattern "$file_path" "\bBuildContext\b" \
      "[${display_name}] Data: BuildContext use prohibited"
    check_pattern "$file_path" "^[[:space:]]*abstract[[:space:]]+([a-z]+[[:space:]]+)?class\b" \
      "[${display_name}] Data: abstract class (separate interface) prohibited (Dart classes define implicit interfaces; use a concrete class + provider override in tests)"
  fi

  # --- Application Layer: flutter_riverpod OK, no Flutter UI ------------------
  if [[ "$layer" == "application" ]]; then
    check_pattern "$file_path" "^import.*package:flutter/" \
      "[${display_name}] Application: package:flutter/ import prohibited (use package:flutter_riverpod/ instead)"
    check_pattern "$file_path" "\bBuildContext\b" \
      "[${display_name}] Application: BuildContext use prohibited"
    check_pattern "$file_path" "\bNavigator\b" \
      "[${display_name}] Application: Navigator use prohibited"
    check_pattern "$file_path" "\bshowDialog\b" \
      "[${display_name}] Application: showDialog use prohibited"
    check_pattern "$file_path" "\bScaffoldMessenger\b" \
      "[${display_name}] Application: ScaffoldMessenger use prohibited"
  fi

  # --- Presentation Layer: no direct Data access, no widget methods -----------
  if [[ "$layer" == "presentation" ]]; then
    check_pattern "$file_path" "^import.*\/data\/.*_repository" \
      "[${display_name}] Presentation: direct repository import prohibited (use Application providers)"

    # Widget Classes NOT Functions: any `Widget xxx(...)` declaration is prohibited,
    # except the StatelessWidget/StatefulWidget `build(BuildContext ...)` override.
    local fn_widgets
    fn_widgets=$(grep -nE '^[[:space:]]*Widget[[:space:]]+[a-zA-Z_][a-zA-Z0-9_]*[[:space:]]*\(' "$file_path" 2>/dev/null \
      | grep -vE 'Widget[[:space:]]+build[[:space:]]*\([[:space:]]*BuildContext' || true)
    if [[ -n "$fn_widgets" ]]; then
      while IFS= read -r line; do
        VIOLATIONS+=("[${display_name}:${line%%:*}] Presentation: function-style widget prohibited — extract to a class extending StatelessWidget/StatefulWidget (Widget Classes NOT Functions)")
      done <<<"$fn_widgets"
    fi
  fi
}

# ---------------------------------------------------------------------------
# Hook mode: triggered by Claude Code PostToolUse
#
# Violations are reported twice on purpose:
#   systemMessage                       -> shown to the user only
#   hookSpecificOutput.additionalContext -> the only field Claude actually reads
#
# Input that cannot be parsed is ignored silently (fail open).
# ---------------------------------------------------------------------------
hook_mode() {
  local input file_path
  input=$(cat)
  file_path=$(jq -r '.tool_input.file_path // empty' <<<"$input" 2>/dev/null) || exit 0

  [[ -z "$file_path" ]] && exit 0

  check_file "$file_path"

  [[ ${#VIOLATIONS[@]} -eq 0 ]] && exit 0

  # Build feedback message, listing at most MAX_LISTED_VIOLATIONS entries.
  local msg total shown
  total=${#VIOLATIONS[@]}
  shown=0
  msg="Architecture Violation Detected:"$'\n'
  for v in "${VIOLATIONS[@]}"; do
    if [[ $shown -ge $MAX_LISTED_VIOLATIONS ]]; then
      break
    fi
    msg+="  - ${v}"$'\n'
    shown=$((shown + 1))
  done
  if [[ $total -gt $MAX_LISTED_VIOLATIONS ]]; then
    msg+="  ... and $((total - MAX_LISTED_VIOLATIONS)) more violations (${total} total)"$'\n'
  fi
  msg+=$'\n'"Fix these violations to maintain clean architecture compliance."

  jq -n --arg msg "$msg" '{
    systemMessage: $msg,
    hookSpecificOutput: {
      hookEventName: "PostToolUse",
      additionalContext: $msg
    }
  }'
}

# ---------------------------------------------------------------------------
# Scan mode: check entire directory
# ---------------------------------------------------------------------------
scan_mode() {
  local target_dir="$1"
  local checked=0

  if [[ ! -d "$target_dir" ]]; then
    echo "Error: directory not found: $target_dir" >&2
    exit 1
  fi

  echo "Scanning: $target_dir"
  echo "========================================="

  while IFS= read -r -d '' file; do
    local rel_path="${file#"$target_dir"/}"
    check_file "$file" "$rel_path"
    ((checked++)) || true
  done < <(find "$target_dir" -name "*.dart" \
    ! -name "*.freezed.dart" \
    ! -name "*.g.dart" \
    -print0 2>/dev/null)

  echo ""
  echo "Results: ${checked} files checked, ${#VIOLATIONS[@]} violations"
  echo ""

  if [[ ${#VIOLATIONS[@]} -eq 0 ]]; then
    echo "All clean architecture rules satisfied."
    exit 0
  fi

  echo "Violations:"
  for v in "${VIOLATIONS[@]}"; do
    echo "  - $v"
  done
  exit 1
}

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--scan" ]]; then
  scan_mode "${2:?Usage: $0 --scan <lib_directory>}"
else
  hook_mode
fi
