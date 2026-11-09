"""同じ case を構成 (arm) ごとに実行して、結果とコストを並べる。

claude plugin eval は子プロセスの引数と設定を固定する (--effort も --settings も渡せず、
CLAUDE.md も読まない) ので、ultracode を有効にした arm を走らせられない。ここでは同じ case
ディレクトリの scaffold・hidden・graders を使い、claude -p を直接起動する。

使い方: python3 compare.py [--case 'plan-implement-*'] [--arms crystallize,ultracode]
                           [--runs 5] [--effort xhigh] [--model opus] [--judge-model haiku] [--budget-usd 20] [-j 2]
--budget-usd は打ち切りが費用の高い arm に偏るので、比べるときは付けない。-j を 2 以上にすると秒は比べられない。
arm:
- crystallize: このプラグインを読み込み、case のプロンプトのまま /crystallize:plan-implement を実行する
- plain: プラグインなし。plan の実装を頼むだけ
- ultracode: プラグインなし。ultracode を有効にする
- thin: ultracode に thin-harness.md を CLAUDE.md として足す

採点は arm で変えない。隠しテスト、元のテスト、コミットしていないこと、case の graders のうち
結果を見るもの (llm / regex / file_exists) を使う。手順を見る tool_used は crystallize にしか
当てはまらないので使わない。すべて合格したら PASS にする。judge のコストは cost に入れない。
打ち切り・異常終了・判定不能・採点の材料に触れた形跡がある回は ERROR にして、PASS 率・隠しテストの通過率・
cost と秒の平均から外し、件数と分かっている cost の合計を別に出す。
結果は results/compare-<時刻>/ に書く (arm-回ごとの trace.jsonl、stderr.log、作業ディレクトリの写し、results.jsonl)。

claude plugin eval との違い: case.yaml の allowed_tools・timeout_seconds・runs は読まない。regex は Python の re で
count:N に対応しない。file_exists は scaffold が作ったファイルも数える。今の case の graders には影響しない。
"""

import argparse
import concurrent.futures
import fnmatch
import json
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from post import read_trace, score_workspace

EVALS = Path(__file__).resolve().parent
WRITE_LOCK = threading.Lock()
PLUGIN = EVALS.parent
CONFIG_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
ARMS = {
    "crystallize": {"plugin": True, "ultracode": False, "rules": False},
    "plain": {"plugin": False, "ultracode": False, "rules": False},
    "ultracode": {"plugin": False, "ultracode": True, "rules": False},
    "thin": {"plugin": False, "ultracode": True, "rules": True},
}
TOOLS = ["Read", "Glob", "Grep", "Skill", "Agent", "Bash", "Write", "Edit", "ToolSearch", "Workflow",
         "TodoWrite", "TaskCreate", "TaskGet", "TaskList", "TaskUpdate", "TaskStop"]
# 実行者の環境から持ち込むのは認証と実行に要るものだけ (CLAUDE_CODE_PLUGIN_DIRS などを子に渡さない)
ENV_KEEP = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR", "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_OAUTH_TOKEN")
ENV_KEEP_PREFIX = ("ANTHROPIC_", "CLAUDE_CODE_USE_")
TIMEOUT_SECONDS = 14400
# handles-gap の grader が plan-implement の手順を採点基準にしていて、他の arm を公平に測れない
EXCLUDED_CASES = {"plan-implement-table-gap"}
NEUTRAL = [
    ("フェーズ 5 で go / no-go を求めたら、そこで止まってください。",
     "実装が終わったらコミットせず、コミットしてよいかの go / no-go を求めて、そこで止まってください。"),
    ("フェーズ 5 より前に", "go / no-go を求める前に"),
    ("また plan-implement の手順が作業の停止を求める場面 (差し戻しの上限、要件と矛盾する逸脱)",
     "また作業を止めるべき場面 (同じ失敗を直しきれないとき、要件と矛盾する逸脱)"),
]


def child_env():
    env = {k: v for k, v in os.environ.items() if k in ENV_KEEP or k.startswith(ENV_KEEP_PREFIX)}
    # 既定の 10 分だと、最後のターンのあとも動いている workflow が途中で打ち切られる
    env["CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS"] = str(TIMEOUT_SECONDS * 1000)
    env["ENABLE_CLAUDEAI_MCP_SERVERS"] = "false"
    # sandbox が home の読み取りを塞ぐので、git が ~/.gitconfig を読みに行かないようにする
    env.update({
        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "core.excludesFile", "GIT_CONFIG_VALUE_0": "/dev/null",
        "GIT_CONFIG_KEY_1": "core.attributesFile", "GIT_CONFIG_VALUE_1": "/dev/null",
        "GIT_AUTHOR_NAME": "eval", "GIT_AUTHOR_EMAIL": "eval@localhost",
        "GIT_COMMITTER_NAME": "eval", "GIT_COMMITTER_EMAIL": "eval@localhost",
    })
    return env


def read_prompt(case_dir):
    lines = (case_dir / "case.yaml").read_text().splitlines()
    start = lines.index("  prompt: |") + 1
    return "\n".join(line[4:] for line in lines[start:]).strip()


def neutral_prompt(prompt):
    """/crystallize:plan-implement を名指しするプロンプトを、スキルに触れない同じ依頼へ書き換える"""
    prompt = re.sub(r"^/crystallize:plan-implement (\S+)", r"\1 の計画を実装してください。", prompt)
    for old, new in NEUTRAL:
        prompt = prompt.replace(old, new)
    if re.search(r"フェーズ|plan-implement|/crystallize:", prompt):
        raise ValueError(f"書き換えられない語が残っている: {prompt}")
    return prompt


def read_graders(case_dir):
    graders = []
    for path in sorted((case_dir / "graders").glob("*.md")):
        _, front, body = path.read_text().split("---\n", 2)
        grader = dict(line.split(": ", 1) for line in front.splitlines() if ": " in line)
        grader["name"], grader["body"] = path.stem, body.strip()
        graders.append(grader)
    return graders


def target_text(spec, last_message, cwd):
    """target / focus の値が { source: file, path: x } ならそのファイルを、無ければ最後のメッセージを返す"""
    match = re.search(r"path:\s*([^\s}]+)", spec or "")
    if not match:
        return last_message
    path = cwd / match.group(1)
    return path.read_text() if path.is_file() else ""


def judge(rubric, evidence, model):
    """判定は 3 票の多数決 (claude plugin eval の llm grader と同じ)。票が揃わなければ None (判定不能) を返す"""
    prompt = f"次の基準で下の内容を判定し、最後の行に PASS か FAIL だけを書いてください。\n\n# 基準\n{rubric}\n\n# 内容\n{evidence}"
    votes = []
    for _ in range(6):  # 失敗した呼び出しの分は引き直す
        try:
            proc = subprocess.run(
                ["claude", "-p", prompt, "--model", model, "--tools", "", "--setting-sources", "project", "--no-session-persistence"],
                cwd=tempfile.gettempdir(), env=child_env(), capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            continue
        lines = proc.stdout.strip().splitlines()
        vote = re.findall(r"\b(PASS|FAIL)\b", lines[-1]) if proc.returncode == 0 and lines else []
        if vote:
            votes.append(vote[-1] == "PASS")
        if len(votes) == 3:
            return sum(votes) >= 2
    return None


def run_grader(grader, last_message, cwd, judge_model):
    kind = grader["type"]
    if kind == "llm":
        return judge(grader["body"], target_text(grader.get("focus"), last_message, cwd), judge_model)
    if kind == "regex":
        flags = re.IGNORECASE if "i" in grader.get("flags", "") else 0
        found = re.search(grader["pattern"].strip("'\""), target_text(grader.get("target"), last_message, cwd), flags)
        return not found if grader.get("match") == "not_contains" else bool(found)
    if kind == "file_exists":
        return any(cwd.glob(grader["path"])) == (grader.get("exists", "true") != "false")
    raise ValueError(f"{grader['name']}: 未対応の grader {kind}")


def pass_rate(log):
    """unittest のログから通過率を返す。読み込みで全滅すると総数が 1 になるので、合計せず回ごとの率で比べる"""
    ran = re.search(r"Ran (\d+) test", log)
    total = int(ran.group(1)) if ran else 0
    failed = re.search(r"FAILED \((.*)\)", log)
    bad = sum(int(n) for n in re.findall(r"(?:failures|errors)=(\d+)", failed.group(1))) if failed else 0
    return (total - bad) / total if total else 0.0


def last_result(trace):
    result = {}
    for line in trace.read_text(errors="replace").split("\n"):
        try:
            event = json.loads(line)
        except ValueError:
            continue  # 空行や途中で切れた行
        # エラーや background のあとに、空の result (num_turns 0) が続くことがある
        if event.get("type") == "result" and (event.get("num_turns") or event.get("is_error") or not result):
            result = event
    return result


def project_slug(path):
    return re.sub(r"[^a-zA-Z0-9]", "-", str(path))


def saw_scoring_material(trace, session_id, cwd):
    """隠しテストや参照解に触れた形跡を探す。workflow の subagent の呼び出しは trace に出ないので、セッションの記録も見る"""
    # 開発中のセッションの記録にも隠しテストの本文が残るので、このリポジトリの記録を読んだ形跡も数える
    # 権限の拒否の文は deny の規則 (`Read(//…/evals/**)`) を引用するので、その形だけは数えない
    # このリポジトリの evals/ だけを見る。v0.17.0 から spec のスキルが `evals/upstream-installments/protocol.md` を名指しするので、
    # plugin の写し (evals/ を除いて写す) の同じパスを開こうとしただけで ERROR にしないため
    pattern = re.compile(rf"test_hidden\.py|test_intent\.py|{re.escape(str(EVALS))}/(?!\*\*\))|projects/{project_slug(PLUGIN.parents[1])}")
    session = CONFIG_DIR / "projects" / project_slug(cwd) / str(session_id)
    paths = [trace, session.with_name(session.name + ".jsonl"), *session.rglob("*.jsonl")]
    return any(pattern.search(p.read_text(errors="replace")) for p in paths if p.is_file())


def git(cwd, *args):
    return subprocess.run(["git", "-c", "core.fsmonitor=false", *args], cwd=cwd, env=child_env(),
                          capture_output=True, text=True, check=True).stdout.strip()


def settings_for(arm, plugin=PLUGIN):
    # plugin なしの arm からは plugin 全体を、plugin の arm からは採点の材料がある evals/ を読めなくする。
    # インストール済みの cache にも同じものがある。plugin は読み込む plugin の場所 (版を差し替えた写しのことがある)
    hidden_root = EVALS if arm["plugin"] else PLUGIN
    allow_read = [str(plugin / "skills")] if arm["plugin"] else []
    deny = [f"Read(/{hidden_root}/**)", f"Edit(/{PLUGIN}/**)", f"Edit(/{plugin}/**)","Read(~/.claude/plugins/**)", f"Read(/{CONFIG_DIR}/plugins/**)"]
    return {
        "ultracode": arm["ultracode"],
        "autoMemoryEnabled": False,
        "permissions": {"allow": TOOLS, "deny": deny},
        "sandbox": {
            "enabled": True,
            "failIfUnavailable": True,
            "allowUnsandboxedCommands": False,
            "filesystem": {"denyRead": ["~/"], "allowRead": allow_read},
        },
    }


def run_claude(command, cwd, trace, env=None):
    """claude を実行して異常の説明 (無ければ None) を返す。時間切れは SIGINT でターンを閉じさせ、result を残す"""
    stderr_log = trace.with_name("stderr.log")
    # stderr をパイプにすると、それを継承した孫プロセスが残っている間は終了を待ち続ける
    with trace.open("w") as stream, stderr_log.open("w") as errors:
        proc = subprocess.Popen(command, cwd=cwd, env={**child_env(), **(env or {})}, stdin=subprocess.DEVNULL, stdout=stream, stderr=errors)
        try:
            proc.wait(timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            return f"timed out after {TIMEOUT_SECONDS}s"
    return f"exit {proc.returncode}: {stderr_log.read_text(errors='replace')[-500:]}" if proc.returncode else None


def run_one(case_dir, arm_name, index, args, out_dir):
    """例外で残りの回を止めないよう、ここで受けて ERROR の行にする"""
    run_dir = out_dir / case_dir.name / f"{arm_name}-{index}"
    try:
        result = score_run(case_dir, arm_name, index, args, run_dir)
    except Exception as exc:
        trace = run_dir / "trace.jsonl"
        cost = last_result(trace).get("total_cost_usd") if trace.is_file() else None
        result = {"case": case_dir.name, "arm": arm_name, "run": index, "verdict": "ERROR",
                  "error": f"{type(exc).__name__}: {exc}", "cost_usd": cost}
    with WRITE_LOCK, (out_dir / "results.jsonl").open("a") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")
    print(f"{case_dir.name} {arm_name}-{index}: {result['verdict']} {result['error'] or ''}", file=sys.stderr, flush=True)
    return result


def score_run(case_dir, arm_name, index, args, run_dir):
    arm = ARMS[arm_name]
    run_dir.mkdir(parents=True)
    trace = run_dir / "trace.jsonl"
    prompt = read_prompt(case_dir)
    if not arm["plugin"]:
        prompt = neutral_prompt(prompt)
    tmp = tempfile.mkdtemp()
    # 並行した回が sandbox の TMPDIR を共有しないように分ける (upstream.py と同じ。短いパスでないと効かない)
    Path("/private/tmp/czr").mkdir(exist_ok=True)
    run_tmp = tempfile.mkdtemp(prefix="c", dir="/private/tmp/czr")
    try:
        cwd = Path(tmp).resolve()
        subprocess.run(["bash", str(case_dir / "scaffold.sh")], cwd=cwd, env=child_env(), check=True, capture_output=True)
        if arm["rules"]:
            shutil.copy(EVALS / "thin-harness.md", cwd / "CLAUDE.md")
            git(cwd, "add", "CLAUDE.md")
            git(cwd, "-c", "user.name=eval", "-c", "user.email=eval@localhost", "commit", "-q", "--amend", "--no-edit")
        head = git(cwd, "rev-parse", "HEAD")

        command = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose", "--max-turns", "200",
                   "--permission-mode", "dontAsk", "--setting-sources", "project", "--effort", args.effort,
                   "--settings", json.dumps(settings_for(arm))]
        if arm["plugin"]:
            command += ["--plugin-dir", str(PLUGIN)]
        if args.model:
            command += ["--model", args.model]
        if args.budget_usd:
            command += ["--max-budget-usd", str(args.budget_usd)]
        started = time.monotonic()
        error = run_claude(command, cwd, trace, {"CLAUDE_CODE_TMPDIR": run_tmp})
        seconds = round(time.monotonic() - started)
        shutil.copytree(cwd, run_dir / "cwd", symlinks=True, ignore=shutil.ignore_patterns(".git", "__pycache__", ".claude"))

        result = last_result(trace)
        if not result:
            error = error or "result イベントが無い"
        elif result.get("is_error") or not result.get("total_cost_usd"):  # cost 0 は API に一度も届かなかった回
            error = f"{error or 'result'}: {result.get('subtype')} (cost {result.get('total_cost_usd')}) {(result.get('result') or '')[:200]}"
        if saw_scoring_material(trace, result.get("session_id"), cwd):
            error = error or "採点の材料に触れた形跡がある"
        last_message = result.get("result") or ""
        hidden_ok, hidden_log, orig_ok, orig_log = score_workspace(case_dir, cwd)
        no_commit = git(cwd, "rev-parse", "HEAD") == head
        graders = {g["name"]: run_grader(g, last_message, cwd, args.judge_model)
                   for g in read_graders(case_dir) if g["type"] != "tool_used"}
    finally:
        # 孫プロセスがまだ書いていても、採点済みの結果を失わない
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(run_tmp, ignore_errors=True)
    undecided = [name for name, value in graders.items() if value is None]
    if undecided:
        error = error or f"判定不能: {undecided}"
    launches, model_cost = read_trace(trace)
    return {
        "case": case_dir.name, "arm": arm_name, "run": index, "error": error,
        "verdict": "ERROR" if error else "PASS" if hidden_ok and orig_ok and no_commit and all(graders.values()) else "FAIL",
        "hidden_rate": pass_rate(hidden_log), "hidden_log": hidden_log,
        "fixture_tests_passed": orig_ok, "fixture_tests_log": orig_log, "no_commit": no_commit, "graders": graders,
        "cost_usd": result.get("total_cost_usd"), "model_cost": model_cost, "seconds": seconds, "launches": launches,
        "result_subtype": result.get("subtype"), "last_message": last_message,
    }


def print_table(results):
    print("| case | arm | PASS | ERROR | 隠しテスト通過率 | 元のテスト | コミットなし | graders | cost USD (平均) | 秒 (平均) | Workflow | Agent |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    keys = sorted({(r["case"], r["arm"]) for r in results})
    for case, arm in keys:
        runs = [r for r in results if (r["case"], r["arm"]) == (case, arm)]
        ok = [r for r in runs if r["verdict"] != "ERROR"]
        n = len(ok)
        grader_counts = [v for r in ok for v in r["graders"].values()]
        costs = [r["cost_usd"] for r in ok if r["cost_usd"] is not None]
        error_cost = sum(r["cost_usd"] or 0 for r in runs if r["verdict"] == "ERROR")
        mean = lambda values, fmt: format(statistics.mean(values), fmt) if values else "-"
        print(f"| {case} | {arm} | {sum(r['verdict'] == 'PASS' for r in ok)}/{n} | {len(runs) - n} "
              f"| {mean([r['hidden_rate'] for r in ok], '.0%')} "
              f"| {sum(r['fixture_tests_passed'] for r in ok)}/{n} | {sum(r['no_commit'] for r in ok)}/{n} "
              f"| {sum(grader_counts)}/{len(grader_counts)} "
              f"| {mean(costs, '.2f')}{f' (+ERROR {error_cost:.2f})' if error_cost else ''} | {mean([r['seconds'] for r in ok], '.0f')} "
              f"| {mean([r['launches'].get('Workflow', 0) for r in ok], '.1f')} "
              f"| {mean([r['launches'].get('Agent', 0) for r in ok], '.1f')} |")


def main():
    parser = argparse.ArgumentParser(description="case を arm ごとに実行して比べる")
    parser.add_argument("--case", default="plan-implement-midsize")
    parser.add_argument("--arms", default=",".join(ARMS))
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--effort", default="xhigh")
    parser.add_argument("--model")
    parser.add_argument("--judge-model", default="haiku")
    parser.add_argument("--budget-usd", type=float, help="1 回の実行あたりの上限")
    parser.add_argument("-j", "--concurrency", type=int, default=1)
    args = parser.parse_args()

    cases = [d for d in sorted(EVALS.iterdir()) if (d / "case.yaml").is_file() and fnmatch.fnmatch(d.name, args.case)
             and d.name not in EXCLUDED_CASES]
    # 回ごとに arm を巡る。arm ごとにまとめると、後の arm だけレート制限に当たる
    jobs = [(c, arm, i) for c in cases for i in range(args.runs) for arm in args.arms.split(",")]
    out_dir = EVALS / "results" / time.strftime("compare-%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True)
    with concurrent.futures.ThreadPoolExecutor(args.concurrency) as pool:
        results = list(pool.map(lambda job: run_one(*job, args, out_dir), jobs))
    print_table(results)
    print(f"\n{out_dir}")


if __name__ == "__main__":
    main()
