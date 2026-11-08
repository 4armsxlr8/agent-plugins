"""claude plugin eval の結果に、実行しないと分からない採点を書き足す。

使い方: python3 post.py <--json で書いた結果ファイル>
前提: eval を --keep-temp 付きで実行していること。

各ケースの各回について、残された作業ディレクトリを一時ディレクトリへ写してから
- hidden/ の隠しテストを実行する
- fixture/tests/ の元のテストを、結果の作業ディレクトリに対して実行する
  (既存のテストファイルへの追記は許し、元のアサーションを弱めた改変は落とす)
- trace から Skill / Agent / Workflow の起動回数 (メインループから出たものだけ) とモデル別のコストを読む
総合判定 (verdict) は、ハーネスの grader がすべて合格し、隠しテストと元のテストも通ったときだけ PASS にする。
版どうしの比較はこの列とコスト・時間で行う。turn 数はメインループしか数えないので比較に使わない。
結果は <結果ファイル>.post.json に書き、表を標準出力に出す。
残された作業ディレクトリの中では git を動かさない (ハーネスの警告どおり)。
"""

import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path


def run_tests(src, workspace, name):
    """src のテストを workspace/<name> に写し、workspace をカレントにして実行する"""
    shutil.copytree(src, workspace / name, ignore=shutil.ignore_patterns("__pycache__"))
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", name],
            cwd=workspace, capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return False, "timed out after 120s"
    return proc.returncode == 0, proc.stderr


def score_workspace(case_dir, cwd):
    """cwd を一時ディレクトリへ写し、hidden/ と fixture/tests/ を実行する"""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "cwd"
        shutil.copytree(cwd, workspace, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        hidden_ok, hidden_log = run_tests(case_dir / "hidden", workspace, "_hidden")
        fixture_tests = case_dir / "fixture" / "tests"
        orig_ok, orig_log = run_tests(fixture_tests, workspace, "_orig_tests") if fixture_tests.is_dir() else (True, "")
    return hidden_ok, hidden_log, orig_ok, orig_log


def read_trace(trace_path):
    """メインループから出た Skill (スキル名ごと)・Agent・Workflow の起動回数、モデル別のコストを返す"""
    launches = Counter()
    model_cost = {}
    for line in Path(trace_path).read_text(errors="replace").split("\n"):
        try:
            event = json.loads(line)
        except ValueError:
            continue  # 空行や途中で切れた行
        if event.get("type") == "result":
            model_cost = {m: round(u.get("costUSD", 0), 4) for m, u in (event.get("modelUsage") or {}).items()}
        # subagent の中の呼び出しは parent_tool_use_id を持つので数えない
        if event.get("type") != "assistant" or event.get("parent_tool_use_id"):
            continue
        for block in event.get("message", {}).get("content", []):
            if block.get("type") != "tool_use":
                continue
            if block["name"] == "Skill":
                launches["Skill:" + block["input"].get("skill", "?")] += 1
            elif block["name"] in ("Agent", "Task"):
                launches["Agent"] += 1
            elif block["name"] == "Workflow":
                launches["Workflow"] += 1
    return dict(launches), model_cost


def post_run(case_dir, run):
    trace = Path(run.get("tracePath") or "")
    if run.get("error") or not trace.is_file():
        return {"verdict": "ERROR", "error": run.get("error") or "trace なし (--keep-temp を付けたか)"}
    try:
        kept = trace.parents[1]
        for d in (kept, kept / "sealed"):
            d.chmod(0o700)
        hidden_ok, hidden_log, orig_ok, orig_log = score_workspace(case_dir, kept / "sealed" / "home" / "cwd")
        launches, model_cost = read_trace(trace)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"verdict": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
    graders_ok = all(g["passed"] for g in run.get("graders", []) if g.get("scored", True))
    return {
        "verdict": "PASS" if graders_ok and hidden_ok and orig_ok else "FAIL",
        "hidden_passed": hidden_ok,
        "hidden_summary": (hidden_log.strip().splitlines() or [""])[-1],
        "hidden_log": hidden_log,
        "fixture_tests_passed": orig_ok,
        "fixture_tests_log": orig_log,
        "launches": launches,
        "model_cost": model_cost,
    }


def main(result_path):
    result = json.loads(Path(result_path).read_text())
    root = Path(result["suite"]["root"])
    rows = []
    for case in result["cases"]:
        case_dir = root / case["dir"]
        for i, run in enumerate(case["arms"]["with"]):
            post = post_run(case_dir, run)
            run["post"] = post
            rows.append((case["name"], i, run, post))
    Path(result_path + ".post.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))

    print("| case | run | verdict | grader | hidden | 元のテスト | cost USD (モデル別) | 秒 | 起動 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for name, i, run, post in rows:
        launches = ", ".join(f"{k}×{v}" for k, v in sorted(post.get("launches", {}).items()))
        costs = ", ".join(f"{m.replace('claude-', '')} {c:.2f}" for m, c in post.get("model_cost", {}).items())
        print(f"| {name} | {i} | {post['verdict']} | {run.get('score') or 0:.2f} "
              f"| {post.get('hidden_summary', post.get('error'))} "
              f"| {'OK' if post.get('fixture_tests_passed') else 'NG'} "
              f"| {run.get('costUsd') or 0:.2f} ({costs}) | {run.get('durationSeconds')} | {launches} |")


if __name__ == "__main__":
    main(sys.argv[1])
