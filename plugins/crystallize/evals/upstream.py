"""spec と plan を作る上流工程の価値を測る。

plan-implement-midsize と同じ機能 (部分返金) を、依頼文だけから始めて実装させる。依頼文には他のコードとつなぐための
名前だけを書き、端数処理や集計の扱いなどの判断は書かない。採点は 2 つ。midsize の隠しテストと、upstream-partial-refund の
意図 5 件 (依頼文に無く、モデルの既定の判断と必ずしも一致しないもの)。後者が、聞き出さないと実装しにくい判断の捕捉数になる。
実装工程の差を混ぜないよう、実装はどの条件も plugin なしの claude にさせる。guess と ask は依頼と同じセッションで続けて実装し、draft、spec、crystallize は新しいセッションが文書を読んで実装する。

条件:
- guess: 質問できない。判断をすべて自分で決めて実装する
- ask: 実装の前に自由に質問できる
- draft: ask と同じように質問したあと短い spec を書き、依頼者役の照合を受ける。新しいセッションがその spec を実装する
- spec: /crystallize:spec で spec を作り、plan を作らずに、新しいセッションがその spec (と隣の ledger) を読んで実装する
- crystallize: /crystallize:spec と /crystallize:plan-create で spec と plan を作り、新しいセッションがその plan (と plan が指す spec や ledger) を読んで実装する
- full: crystallize と同じ spec と plan を /crystallize:plan-implement で実装する
質問には、依頼者役の claude がケースごとの意図を持って答える。partial-refund の意図は、受け入れ基準表を除く midsize の spec と守るべき既存挙動、追加の意図 5 件。
聞かれたことにだけ答えるよう指示している (強制はしておらず、走行後に監査する)。広い問いには 1 つしか答えない。一覧や草案の扱いは --oracle-rule で選ぶ。
- review-all: 一覧と spec の草案を読み、食い違いをすべて指摘する。一覧や草案を読む依頼者の上限にあたる
- question-only: 1 つの論点を名指しした問いと広い問いにだけ答え、一覧や草案は読まない。草案は渡さず、決めたこととして書かれた潜在の判断も渡さない。読み飛ばす依頼者の下限にあたる
意図 5 件は crystallize の試走を見たあとで選んだ。捕捉数はこの 5 件についての数で、質問の網羅性の一般論にはならない。

使い方: python3 upstream.py [--case partial-refund] [--conditions guess,ask,draft,spec,crystallize,full] [--runs 1] [--effort xhigh] [--model sonnet] [--oracle-model opus] [--oracle-rule review-all] [--budget-usd 20] [-j 2]
同じ文書から枝分かれさせる: python3 upstream.py --case installments --conditions crystallize --branch results/<spec の dir> (spec の各回の続きから plan を作る。full なら crystallize の各回の plan から)
実装者を替える: python3 upstream.py --case installments --replay results/<dir>,results/<dir> --model sonnet --effort medium
追加の依頼: python3 upstream.py --case installments --followup results/<dir>/<条件-回>/cwd --runs 3
ケースは upstream-partial-refund (判断 5 件、下の説明) と upstream-installments (判断 12 件、計画は protocol.md)。
--budget-usd は打ち切りが費用の高い条件に偏るので、比べるときは付けない。-j を 2 以上にすると秒は比べられない。
結果は results/upstream-<ケース>-<時刻>/ に書く (条件-回ごとの trace、依頼者とのやり取り exchanges.jsonl、作業ディレクトリの写し、results.jsonl)。

エージェントは sandbox の TMPDIR に作業ディレクトリを残す。既定の TMPDIR は他のセッションと共有なので、回ごとに CLAUDE_CODE_TMPDIR で別の場所を渡し、回の終わりに消す。他の回の TMPDIR に触れた形跡があれば ERROR にする。

依頼者役は知っている意図に迷わず答えるので、質問できる条件には有利に働く。review-all では、draft、spec、crystallize は草案全体を照合してもらえるが、ask が照合されるのは自分が出した一覧の範囲だけである。実際の依頼者が考えていなかった論点に気づかせる価値は測れない。
"""

import argparse
import concurrent.futures
import contextlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from collections import namedtuple

from compare import ARMS, CONFIG_DIR, EVALS, PLUGIN, child_env, git, last_result, pass_rate, project_slug, run_claude, saw_scoring_material, settings_for
from post import score_workspace

CASE = EVALS / "plan-implement-midsize"
DECISIONS = ("Deadline", "BlankReason", "BeforeIssue", "StatementRefunded", "SchemaVersion")
CONDITIONS = ("guess", "ask", "draft", "spec", "crystallize", "full")
BRANCH_SOURCE = {"crystallize": "spec", "full": "crystallize"}
SPEC = CASE / "fixture/docs/crystallize/specs/partial-refund.md"
PLAN = CASE / "fixture/docs/crystallize/plans/partial-refund.md"
MAX_REPLIES = 24
WRITE_LOCK = threading.Lock()
# 長いパスは短い代替に置き換えられるので短くする
RUN_TMP_ROOT = Path("/private/tmp/czr")
LIMIT = re.compile(r"hit your [^\n]*limit", re.I)
LIMIT_WAIT_SECONDS = 600
# hidden_case は判断によらない隠しテスト、intent_case は判断ごとのテスト。latent は開発者が触れるまで依頼者役に見せない判断
Case = namedtuple("Case", "slug request intent decisions latent hidden_case intent_case followup")
REQUEST = """`billing` パッケージに部分返金を足してください。顧客が商品の一部を返品してきたとき、請求書を取り消さずに、返品された数量の分だけ返金を記録して、売上・税額・顧客の残高の集計を帳簿と合ったままにしたいです。

他のコードとつなぐので、次の名前は揃えてください。
- `billing.refunds.issue_refund(book, invoice_id, quantities, reason, actor, on)`: `quantities` は `line_id` → 返金する数量の dict、`on` は返金日。返金 1 件を表す `Refund` を返す
- `Refund` の属性: `refund_id`, `invoice_id`, `quantities`, `net`, `tax`, `total`, `reason`, `actor`, `issued_on`
- `billing.refunds.refunds_for(book, invoice_id)`
- `billing.refunds.refundable_quantity(book, invoice_id, line_id)`: 請求書の状態によらず、その明細のまだ返金していない数量を返す
- 返金番号の形式: `RF-0001`
- 請求書の状態: `partially_refunded`, `refunded`
- 監査イベント: `refund.issued`。`data` は `refund_id`, `amount`, `reason`
- `receivables.customer_summary` の通貨ごとの行に足す項目: `refunded`"""
EXTRA_INTENT = """## 追加の意図 (上と食い違うときはこちらを優先する)
- 発行日から 180 日を超えた返金は `ValidationError` にする (180 日目までは返金できる)
- `reason` は空でも検査せずに記録する。入力の検査は呼び出し側の責任
- 返金日が発行日より前でも検査せずに記録する。過去の修正を入れることがある
- `receivables.customer_statement` の各行に `refunded` (その請求書の返金の `total` の合計) を足す。`total` と `paid` は変えない
- 保存形式の `schema_version` は 1 のまま変えない。変更前のコードもこの形式を読み続ける"""
FINISH = "実装が終わったらコミットせず、コミットしてよいかの go / no-go を求めて、そこで止まってください。"
NO_ANSWER = "私は質問に答えられません。判断が必要な点は自分で決めて実装してください。"
GUESS_PROMPT = f"{{request}}\n\n{NO_ANSWER}{FINISH}"
ASK_PROMPT = f"{{request}}\n\n実装の前に、判断に必要で私にしか分からないことがあれば質問してください。質問はこの会話に書いて、答えを待ってください。{FINISH}"
DRAFT_PROMPT = "{request}\n\nまだ実装しないでください。判断に必要で私にしか分からないことがあれば質問してください。質問はこの会話に書いて、答えを待ってください。答えが揃ったら、決まったことを `docs/crystallize/specs/{slug}.md` に短い仕様書として書いて、確認を求めてください。別のセッションが同じ作業ツリーでこの仕様書だけを読んで実装します。コミットしないでください。"
# plan-implement-midsize の case.yaml と同じ指示。ユーザーが応答できない実行でフェーズ 5 まで進める
FULL_PROMPT = "/crystallize:plan-implement {plan}\n\nフェーズ 5 で go / no-go を求めたら、そこで止まってください。\nこのケースではユーザーは応答できません。フェーズ 5 より前にユーザーへ確認したくなった点は、あなたの推奨案が採用されたものとして記録して進めてください。ただし spec の改訂を伴う推奨案 (要件や受け入れ基準表の追加・変更) は採用せず、plan の `## Deviations` にスコープ外として記録して進めてください。また plan-implement の手順が作業の停止を求める場面 (差し戻しの上限、要件と矛盾する逸脱) では、推奨案で進めずに止まってください。"
LATENT_CHECK = """開発者が依頼者に送ったメッセージと添付を読み、下の話題のそれぞれについて、開発者が自分から具体的に触れているかを判定してください。関連しそうな一般論だけなら触れていないことにします。

触れている話題は 1 行に 1 つ、次の形で書いてください。無ければ NONE とだけ書いてください。
- 依頼者の判断を求めている (質問している、選択肢に挙げて確認している): `<名前>: ASKED`
- 判断を求めず、決めたこととして書いている: `<名前>: STATED`。一覧全体にまとめて確認を求めているだけの項目もこちら。問いの説明、表、選択肢の得失に出てくるだけで、その話題自体の判断を求めていないものもこちら。「次のラウンドで聞く予定」のような予告で、まだ判断を求めていないものもこちら

# 話題
{topics}"""
ORACLE ="""あなたはソフトウェアの依頼者です。開発者から届いたメッセージに返信してください。あなたの意図は下の「意図」のとおりです。

規則:
- 聞かれたことにだけ、望む結果を短く答える。聞かれていないことを先回りして話さない。意図の文書を丸ごと貼らない
- 「他に要望はありますか」「制約はありますか」のような広い問いには、当てはまるものを 1 つだけ答える
- 意図に書かれていないことを聞かれたら「お任せします」と答える
{review_rules}
- 確認事項がなく、報告や案内だけのメッセージなら、DONE とだけ書く。コミットの go / no-go を聞かれたとき、spec や plan が完成して次の工程を案内しているときも DONE とだけ書く
- ラウンドレポート (HTML) が添えられていたら、その問いごとに答える。形式は `## Decisions` の下に `N. <問いの文>` と次の行の `→ <問いの id>: **<選ぶ選択肢の label>** `<選択肢の id>``。自由記述は `→ <問いの id>:` の次の行に `> <本文>`。選択肢が意図に合わなければ `→ <問いの id>: **前提が違う** `premise`` を選び、次の行の `→ premise:` の下に `> <その問いへの答え>` を書く。その問いについて意図に選択肢より具体的な決まりがあれば、`## Comments` に 1 行で足す。意図に書かれていない問いは推奨のままにして `_(kept as proposed)_` と書く。range は `→ <id>: **<値>**` と書く

# 意図
{intent}

# 届いたメッセージ
{message}
{report}"""
REVIEW_RULES = {
    "review-all": """- 開発者が決めた進め方の一覧を示して確認を求めたときは、意図と食い違うものをすべて指摘する
- spec の草案が添えられていたら、意図と食い違う箇所をすべて指摘する。意図に書かれていない箇所には触れない。食い違いが無ければ他の規則に従う""",
    "question-only": """- 問いとして答えるのは、上の広い問いと、1 つの論点を名指しして判断を求めている文だけ。選択肢の有無は問わない。番号付きの項目がそれぞれ判断を求めていれば、それぞれに答える
- 問いが意図の 1 行に触れたら、チャットでもレポートでも、その行の決まりをまとめて答える。意図の別の行には触れない
- 開発者が決めたこととして書いた内容 (前提の一覧、表、「〜で進めます」、問いに添えた説明、ラウンドレポートの前提欄や「定めたこと」) は読まない。意図と食い違っていても指摘しない。問いへの答えの中で、問われていない論点に触れない
- 一覧、表、前提のまとめを確認するよう求める文 (「違っていれば指摘してください」「この前提で進めてよいですか」) は問いではない。ほかに問いがあれば問いにだけ答え、なければ「はい、それで結構です」とだけ答える
- 書き終えた仕様書の確認や確定を求める文 (「仕様書を確認してください」「認識が揃ったと一言ください」「/plan-create に進みます」) も問いではない。ほかに問いがあれば問いにだけ答え、なければ DONE とだけ書く
- ラウンドレポートの問いにも同じ区別を当てる。前提のまとめのずれを尋ねる問いは推奨のままにする。推奨の無い問いで意図に書かれていなければ、先頭の選択肢を選ぶ (`_(kept as proposed)_` にしない)。選択肢の説明や得失も読まない。「前提が違う」を選ぶのは、問いの文が求める論点について意図が選択肢と食い違うときだけで、`## Comments` にはその問いへの答えだけを書く""",
}


def oracle(message, cwd, seen, model, case, unlocked, rule):
    """依頼者役の返信と記録する項目を返す。まだ見せていないラウンドレポートがあれば添える。review-all なら spec の草案も添える"""
    review_all = rule == "review-all"
    specs = cwd / "docs/crystallize/specs"
    reports = sorted(specs.glob("**/round-*.html"), key=lambda p: p.stat().st_mtime)
    fresh_reports = [p for p in reports if (p, p.stat().st_mtime) not in seen]
    fresh_drafts = [p for p in specs.glob("*.md") if (p, p.stat().st_mtime) not in seen]
    seen.update((p, p.stat().st_mtime) for p in fresh_reports + fresh_drafts)
    report = ""
    if fresh_reports:
        # doc-code の本文は <script type="text/plain"> に入っているので残す
        html = re.sub(r"<style\b.*?</style>|<script(?![^>]*text/plain)\b.*?</script>", "", fresh_reports[-1].read_text(errors="replace"), flags=re.S)
        report = f"\n# 添えられたラウンドレポート\n{html}"
    attached = fresh_reports[-1:] + (fresh_drafts if review_all else [])
    for draft in attached[len(fresh_reports[-1:]):]:
        report += f"\n# 添えられた spec の草案\n{draft.read_text(errors='replace')}"
    # STATED はあとで問われたら ASKED に変わる。question-only では STATED のままなら依頼者は知らない
    locked = [item for item in case.latent if unlocked.get(item["name"]) != "ASKED"]
    text = f"{message}\n{report}"
    newly, classifier = raised_topics(text, locked, model)
    unlocked.update(newly)
    known = [f"- {item['intent']}" for item in case.latent if unlocked.get(item["name"]) == "ASKED" or (review_all and item["name"] in unlocked)]
    intent = "\n".join([case.intent, *known])
    reply = ask_model(ORACLE.format(review_rules=REVIEW_RULES[rule], intent=intent, message=message, report=report), model)
    return {"reply": reply, "attached": [p.name for p in attached], "raised": newly,
            "classifier": classifier, "read_chars": len(re.sub(r"<[^>]+>", "", text))}


def raised_topics(text, locked, model):
    """開発者が自分から触れた潜在の判断 (名前 → ASKED か STATED) と判定の原文を返す。触れるまでは返信役に見せないので、依頼者から言い出すことがない"""
    if not locked:
        return {}, ""
    topics = "\n".join(f"- {item['name']}: {item['topic']}" for item in locked)
    prompt = f"{LATENT_CHECK.format(topics=topics)}\n\n# 開発者のメッセージと添付\n{text}"
    reply = ask_model(prompt, model)
    raised = {}
    for item in locked:
        line = re.search(rf"^\W*{item['name']}\b(.*)$", reply, re.M)
        if line:
            raised[item["name"]] = "ASKED" if "ASKED" in line.group(1) else "STATED"
    return raised, reply


def ask_model(prompt, model):
    """道具なしの claude に 1 回聞く。上限に当たっている間は待つ"""
    attempts = 0
    while attempts < 3:
        try:
            proc = subprocess.run(["claude", "-p", prompt, "--model", model, "--tools", "", "--setting-sources", "project", "--no-session-persistence"],
                                  cwd=tempfile.gettempdir(), env=child_env(), capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            attempts += 1
            continue
        if LIMIT.search(proc.stdout + proc.stderr):
            time.sleep(LIMIT_WAIT_SECONDS)
            continue
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
        attempts += 1
    raise RuntimeError("依頼者役が返信しなかった")


def captured_decisions(log, decisions):
    """意図のテストが通った判断の名前を返す。読み込みで全滅したら空"""
    if "_FailedTest" in log or not re.search(r"Ran \d+ test", log):
        return []
    return [d for d in decisions if not re.search(rf"^(?:FAIL|ERROR): .*\b{d}\b", log, re.M)]


@contextlib.contextmanager
def workspace():
    """作業ディレクトリ。孫プロセスがまだ書いていても、採点済みの結果を失わない"""
    tmp = tempfile.mkdtemp()
    try:
        yield Path(tmp).resolve()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def commit_copy(source, cwd, message):
    shutil.copytree(source, cwd, dirs_exist_ok=True, symlinks=True)
    git(cwd, "init", "-q")
    git(cwd, "add", "-A")
    git(cwd, "commit", "-qm", message)


def good_runs(source):
    """結果ディレクトリの ERROR でない回を返す"""
    rows = [json.loads(line) for line in (source / "results.jsonl").read_text().splitlines()]
    return [r for r in rows if r.get("verdict") != "ERROR"]


def scaffold(cwd, case):
    shutil.copytree(CASE / "fixture", cwd, dirs_exist_ok=True)
    for name in ("plans", "specs"):
        shutil.rmtree(cwd / "docs/crystallize" / name)
    # 部分返金の語が用語集に残っていると、別の機能のケースで読み手を迷わせる
    if case.slug != "partial-refund":
        glossary = cwd / "docs/crystallize/CONTEXT.md"
        glossary.write_text(re.sub(r"^- \*\*返金\*\*.*\n", "", glossary.read_text(), flags=re.M))
    git(cwd, "init", "-q")
    git(cwd, "add", "-A")
    git(cwd, "commit", "-qm", "initial")


class Run:
    """1 回分の claude の起動と集計"""

    def __init__(self, cwd, run_dir, args, case):
        self.cwd, self.run_dir, self.args, self.case = cwd, run_dir, args, case
        self.costs, self.steps, self.replies, self.reply_chars, self.traces = [], 0, 0, 0, []
        self.seen, self.error, self.unlocked, self.waited, self.read_chars = set(), None, {}, 0, 0
        RUN_TMP_ROOT.mkdir(exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(prefix="r", dir=RUN_TMP_ROOT))

    def continue_from(self, source):
        """枝分かれの元の回が依頼者役に見せたものを引き継ぐ。依頼者が知った判断は忘れず、見た文書を添え直さない"""
        exchanges = source / "exchanges.jsonl"
        if exchanges.is_file():
            for line in exchanges.read_text().splitlines():
                self.unlocked.update(json.loads(line)["raised"])
        self.seen.update((p, p.stat().st_mtime) for p in (self.cwd / "docs/crystallize/specs").rglob("*") if p.is_file())

    def contaminated(self):
        """採点の材料や、この回のものでない TMPDIR に触れた形跡を探す。依頼者役への入力は trace に入らない"""
        other_tmp = re.compile(rf"/tmp/claude-501/|/tmp/{RUN_TMP_ROOT.name}/(?!{self.tmp.name})")
        for trace in self.traces:
            session_id = last_result(trace).get("session_id")
            if saw_scoring_material(trace, session_id, self.cwd):
                return "採点の材料に触れた形跡がある"
            session = CONFIG_DIR / "projects" / project_slug(self.cwd) / str(session_id)
            paths = [trace, session.with_name(session.name + ".jsonl"), *session.rglob("*.jsonl")]
            if any(other_tmp.search(p.read_text(errors="replace")) for p in paths if p.is_file()):
                return "他の回の TMPDIR に触れた形跡がある"
        return None

    @property
    def cost(self):
        return sum(self.costs)

    def step(self, prompt, plugin, session=None):
        """claude を 1 回起動して result を返す"""
        self.steps += 1
        trace = self.run_dir / f"step-{self.steps}.jsonl"
        arm = ARMS["crystallize" if plugin else "plain"]
        plugin_dir = self.args.plugin_dir or PLUGIN
        command = ["claude", "-p", "--output-format", "stream-json", "--verbose", "--max-turns", "200",
                   "--permission-mode", "dontAsk", "--setting-sources", "project", "--effort", self.args.effort,
                   "--settings", json.dumps(settings_for(arm, plugin_dir))]
        if plugin:
            command += ["--plugin-dir", str(plugin_dir)]
        if session:
            command += ["--resume", session]
        if self.args.budget_usd:
            command += ["--max-budget-usd", str(self.args.budget_usd)]
        if self.args.model:
            command += ["--model", self.args.model]
        command += ["--", prompt]  # 返信が - で始まっても引数として読まれないように
        problem = run_claude(command, self.cwd, trace, {"CLAUDE_CODE_TMPDIR": str(self.tmp)})
        self.traces.append(trace)
        result = last_result(trace)
        # --resume の total_cost_usd はそのセッションの累計なので、同じセッションの値は置き換える
        cost = result.get("total_cost_usd") or 0
        if LIMIT.search(result.get("result") or ""):
            # 利用の上限。リセットまで待つ。途中まで進んでいたら同じセッションで続きをさせる
            time.sleep(LIMIT_WAIT_SECONDS)
            self.waited += LIMIT_WAIT_SECONDS
            self.steps -= 1
            self.traces.pop()
            worked = cost and (not session or cost > self.costs[-1])
            if not worked:
                return self.step(prompt, plugin, session)
            if session:
                self.costs[-1] = cost
            else:
                self.costs.append(cost)
            trace.rename(trace.with_name(f"limit-{int(time.time())}.jsonl"))
            return self.step("続けてください。", plugin, result.get("session_id"))
        if session:
            self.costs[-1] = cost or self.costs[-1]
        else:
            self.costs.append(cost)
        if result.get("is_error") or not result.get("total_cost_usd"):
            problem = f"{problem or 'result'}: {result.get('subtype')} {(result.get('result') or '')[:200]}"
        self.error = self.error or problem
        return result

    def converse(self, prompt, plugin):
        """依頼者役が DONE と答えるまでやり取りし、最後の result を返す"""
        result = self.step(prompt, plugin)
        # 実装が始まったら依頼者に見せない。guess、draft、spec、crystallize の実装には直してくれる人がいない
        while not self.error and not git(self.cwd, "status", "--porcelain", "--", "billing"):
            try:
                answer = oracle(result.get("result") or "", self.cwd, self.seen, self.args.oracle_model, self.case, self.unlocked, self.args.oracle_rule)
            except RuntimeError as exc:
                self.error = str(exc)
                break
            reply = answer["reply"]
            lines = [re.sub(r"\W", "", line) for line in reply.splitlines() if line.strip()]
            # 説明のあとに DONE を書くことがある。その説明を開発者に届けない。答えのあとの DONE なら答えも落ちるので、監査で本文を読む
            trailing_done = lines[0] != "DONE" and lines[-1] == "DONE"
            with (self.run_dir / "exchanges.jsonl").open("a") as f:
                f.write(json.dumps({"message": result.get("result"), **answer, "trailing_done": trailing_done}, ensure_ascii=False) + "\n")
            self.read_chars += answer["read_chars"]
            if "DONE" in (lines[0], lines[-1]):
                break
            if self.replies == MAX_REPLIES:
                self.error = f"返信が {MAX_REPLIES} 回を超えた"
                break
            self.replies += 1
            self.reply_chars += len(reply)
            result = self.step(reply, plugin, result.get("session_id"))
        return result


def run_condition(condition, run):
    """条件ごとの手順を実行し、実装に入る前までの cost を返す"""
    request = run.case.request
    if condition == "guess":
        run.step(GUESS_PROMPT.format(request=request), plugin=False)
        return 0.0
    if condition == "ask":
        run.converse(ASK_PROMPT.format(request=request), plugin=False)
        if not run.error and not changed_billing(run):
            run.error = "実装しないまま終わった"
        return 0.0
    if condition in ("draft", "spec"):
        if condition == "draft":
            run.converse(DRAFT_PROMPT.format(request=request, slug=run.case.slug), plugin=False)
        else:
            run.converse(f"/crystallize:spec {request}", plugin=True)
        specs = sorted(run.cwd.glob("docs/crystallize/specs/*.md"))
        if not run.error and not specs:
            run.error = "spec が書かれなかった"
        if not run.error and list(run.cwd.glob("docs/crystallize/plans/*.md")):  # plan が混ざると crystallize と区別できない
            run.error = "spec のセッションが plan まで作った"
        if not run.error and changed_billing(run):
            run.error = "実装の工程より前に billing を変更した"
        upstream_cost = run.cost
        if not run.error:
            snapshot(run)
            run.step(implement_prompt(specs, run.cwd, "仕様"), plugin=False)
        return upstream_cost
    specs = sorted(run.cwd.glob("docs/crystallize/specs/*.md"))
    if not specs:  # 枝分かれなら元の回の spec がある
        run.converse(f"/crystallize:spec {request}", plugin=True)
        specs = sorted(run.cwd.glob("docs/crystallize/specs/*.md"))
    if not run.error and not specs:
        run.error = "spec が書かれなかった"
    if not run.error and not list(run.cwd.glob("docs/crystallize/plans/*.md")):
        run.converse("/crystallize:plan-create " + " ".join(str(p.relative_to(run.cwd)) for p in specs), plugin=True)
    plans = sorted(run.cwd.glob("docs/crystallize/plans/*.md"))
    if not run.error and not plans:
        run.error = "plan が書かれなかった"
    if not run.error and changed_billing(run):
        run.error = "実装の工程より前に billing を変更した"
    upstream_cost = run.cost
    if not run.error:
        snapshot(run)
        if condition == "full":
            run.step(FULL_PROMPT.format(plan=" ".join(str(p.relative_to(run.cwd)) for p in plans)), plugin=True)
        else:
            run.step(implement_prompt(plans, run.cwd, "計画"), plugin=False)
    return upstream_cost


def changed_billing(run):
    return bool(git(run.cwd, "status", "--porcelain", "--", "billing"))


def implement_prompt(documents, cwd, kind):
    paths = " ".join(str(p.relative_to(cwd)) for p in documents)
    return f"{paths} の{kind}を実装してください。\n\n{NO_ANSWER}{FINISH}"


def snapshot(run):
    """実装の工程に入る前の作業ディレクトリを残す。実装者を替えて同じ文書から実装し直すのに使う"""
    shutil.copytree(run.cwd, run.run_dir / "pre-impl", symlinks=True, ignore=shutil.ignore_patterns(".git", "__pycache__", ".claude"))


def score_tree(case, cwd):
    """判断によらない隠しテストと判断ごとのテストで採点する"""
    hidden_ok, hidden_log, orig_ok, orig_log = score_workspace(case.hidden_case, cwd)
    _, intent_log, _, _ = score_workspace(case.intent_case, cwd)
    return {
        "hidden_ok": hidden_ok, "decisions": captured_decisions(intent_log, case.decisions), "intent_log": intent_log,
        "hidden_rate": pass_rate(hidden_log), "failed_tests": re.findall(r"^(?:FAIL|ERROR): (\S+ \(\S+\))", hidden_log, re.M),
        "hidden_log": hidden_log, "fixture_tests_passed": orig_ok, "fixture_tests_log": orig_log,
    }


def finish(run, cwd):
    """作業ディレクトリを結果に写し、汚染を確かめて、回の TMPDIR を消す"""
    shutil.copytree(cwd, run.run_dir / "cwd", symlinks=True, ignore=shutil.ignore_patterns(".git", "__pycache__", ".claude"))
    run.error = run.error or run.contaminated()
    shutil.rmtree(run.tmp, ignore_errors=True)


def score(condition, index, args, run_dir, case, source=None):
    run_dir.mkdir(parents=True)
    with workspace() as cwd:
        if source:
            commit_copy(source / "pre-impl", cwd, "before implementation")
        else:
            scaffold(cwd, case)
        head = git(cwd, "rev-parse", "HEAD")
        run = Run(cwd, run_dir, args, case)
        if source:
            run.continue_from(source)
        started = time.monotonic()
        upstream_cost = run_condition(condition, run)
        seconds = round(time.monotonic() - started) - run.waited
        finish(run, cwd)
        scored = score_tree(case, cwd)
        no_commit = git(cwd, "rev-parse", "HEAD") == head
    return {
        "condition": condition, "run": index, "source": str(source) if source else None, "oracle_model": args.oracle_model, "oracle_rule": args.oracle_rule,
        "variant": args.variant, "report_shape": report_shape(run_dir / "cwd"),
        "error": run.error, "no_commit": no_commit,
        "verdict": "ERROR" if run.error else "PASS" if scored["hidden_ok"] and scored["fixture_tests_passed"] and no_commit else "FAIL",
        **scored, "raised": run.unlocked, "read_chars": run.read_chars,
        "replies": run.replies, "reply_chars": run.reply_chars, "steps": run.steps,
        "cost_usd": run.cost, "upstream_cost_usd": upstream_cost, "seconds": seconds, "waited_seconds": run.waited,
    }


REPORT_MARKERS = {"questions": r"<doc-ask\b", "frame": r'id="s-frame"', "card": r'class="card"', "premise": r"<strong>前提:",
                  "gain": r"できるようになる", "table": r"<table\b", "code": r"<doc-code\b"}


def report_shape(cwd):
    """ラウンドレポートごとの部品の数と、タグを除いた文字数。短い版が本当に短いかを確かめる"""
    shapes = []
    for path in sorted((cwd / "docs/crystallize/specs").glob("**/round-*.html")):
        html = path.read_text(errors="replace")
        body = re.sub(r"<style\b.*?</style>|<script(?![^>]*text/plain)\b.*?</script>", "", html, flags=re.S)
        shapes.append({"name": path.name, "chars": len(re.sub(r"<[^>]+>", "", body)),
                       **{k: len(re.findall(p, html)) for k, p in REPORT_MARKERS.items()}})
    return shapes


def replay(condition_run, args, out_dir, case):
    """pre-impl の文書から、実装者を替えて実装し直す。文書が同じで実装者だけが違う"""
    run_dir = out_dir / f"{condition_run.name}-{args.model or 'same'}-{args.effort}-{time.monotonic_ns()}"
    run_dir.mkdir(parents=True)
    with workspace() as cwd:
        commit_copy(condition_run / "pre-impl", cwd, "before implementation")
        run = Run(cwd, run_dir, args, case)
        started = time.monotonic()
        plans = sorted(cwd.glob("docs/crystallize/plans/*.md"))
        documents = plans or sorted(cwd.glob("docs/crystallize/specs/*.md"))
        run.step(implement_prompt(documents, cwd, "計画" if plans else "仕様"), plugin=False)
        seconds = round(time.monotonic() - started) - run.waited
        finish(run, cwd)
        scored = score_tree(case, cwd)
    return {"condition": condition_run.name, "source": str(condition_run), "error": run.error, "model": args.model, "effort": args.effort,
            **scored, "cost_usd": run.cost, "seconds": seconds}


def followup(source, arm, index, args, out_dir, case):
    """実装済みの作業ディレクトリに追加の依頼をする。文書を残す arm と消す arm で比べる"""
    run_dir = out_dir / f"{source.parent.name}-{arm}-{index}"
    run_dir.mkdir(parents=True)
    with workspace() as cwd:
        shutil.copytree(source, cwd, dirs_exist_ok=True, symlinks=True)
        if arm == "stripped":
            for name in ("plans", "specs"):
                shutil.rmtree(cwd / "docs/crystallize" / name, ignore_errors=True)
        git(cwd, "init", "-q")
        git(cwd, "add", "-A")
        git(cwd, "commit", "-qm", "implemented")
        run = Run(cwd, run_dir, args, case)
        started = time.monotonic()
        run.step(case.followup, plugin=False)
        seconds = round(time.monotonic() - started) - run.waited
        finish(run, cwd)
        _, follow_log, _, _ = score_workspace(EVALS / f"upstream-{case.slug}/followup", cwd)
        scored = score_tree(case, cwd)
    touched_docs = any(re.search(r"docs/crystallize/(?:specs|plans)", t.read_text(errors="replace")) for t in run.traces)
    return {"workspace": str(source), "arm": arm, "run": index, "error": run.error, "touched_docs": touched_docs,
            "followup_rate": pass_rate(follow_log), "followup_log": follow_log,
            "followup_failed": re.findall(r"^(?:FAIL|ERROR): (\S+ \(\S+\))", follow_log, re.M),
            **scored, "cost_usd": run.cost, "seconds": seconds}


def load_case(name):
    if name == "partial-refund":
        # 受け入れ基準の節だけ除く。スコープ外や用語は依頼者が答えられるように残す
        spec = re.sub(r"^## 受け入れ基準.*?(?=^## )", "", SPEC.read_text(), flags=re.S | re.M)
        intent = "\n\n".join((spec, PLAN.read_text().split("## 実装計画")[0], EXTRA_INTENT))
        return Case("partial-refund", REQUEST, intent, DECISIONS, [], CASE, EVALS / "upstream-partial-refund", None)
    root = EVALS / f"upstream-{name}"
    data = json.loads((root / "case.json").read_text())
    return Case(data["slug"], data["request"], data["intent"], data["decisions"], data["latent"],
                root / "properties", root / "intents", data["followup"])


def run_one(condition, index, args, out_dir, case, source=None):
    run_dir = out_dir / f"{condition}-{index}"
    try:
        result = score(condition, index, args, run_dir, case, source)
    except Exception as exc:
        result = {"condition": condition, "run": index, "variant": args.variant, "verdict": "ERROR", "error": f"{type(exc).__name__}: {exc}", "cost_usd": None}
    with WRITE_LOCK, (out_dir / "results.jsonl").open("a") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")
    print(f"{condition}-{index}: {result['verdict']} {result['error'] or ''}", file=sys.stderr, flush=True)
    return result


def print_table(results):
    print("| 条件 | PASS | ERROR | 捕捉した判断 (回ごと) | 隠しテスト通過率 (回ごと) | 返信回数 | 返信の文字数 | 上流の cost | 全体の cost | 秒 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for condition in sorted({r["condition"] for r in results}):
        runs = [r for r in results if r["condition"] == condition]
        ok = [r for r in runs if r["verdict"] != "ERROR"]
        mean = lambda key, fmt: format(statistics.mean(r[key] for r in ok), fmt) if ok else "-"
        rates = " ".join(format(r["hidden_rate"], ".0%") for r in ok) or "-"
        captured = " ".join(str(len(r["decisions"])) for r in ok) or "-"
        error_cost = sum(r["cost_usd"] or 0 for r in runs if r["verdict"] == "ERROR")
        print(f"| {condition} | {sum(r['verdict'] == 'PASS' for r in ok)}/{len(ok)} | {len(runs) - len(ok)} | {captured} | {rates} | {mean('replies', '.1f')} "
              f"| {mean('reply_chars', '.0f')} | {mean('upstream_cost_usd', '.2f')} | {mean('cost_usd', '.2f')}{f' (+ERROR {error_cost:.2f})' if error_cost else ''} | {mean('seconds', '.0f')} |")


def main():
    parser = argparse.ArgumentParser(description="上流工程の条件ごとに実装させて比べる")
    parser.add_argument("--case", default="partial-refund")
    parser.add_argument("--conditions", default=",".join(CONDITIONS))
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--effort", default="xhigh")
    parser.add_argument("--model")
    parser.add_argument("--oracle-model", default="opus")
    parser.add_argument("--oracle-rule", default="review-all", choices=tuple(REVIEW_RULES))
    parser.add_argument("--budget-usd", type=float, help="claude の起動 1 回あたりの上限")
    parser.add_argument("-j", "--concurrency", type=int, default=1)
    parser.add_argument("--branch", help="この結果ディレクトリの各回の pre-impl を文書として引き継いで --conditions を走らせる")
    parser.add_argument("--replay", help="これらの結果ディレクトリ (カンマ区切り) の pre-impl から、--model と --effort の実装者で実装し直す")
    parser.add_argument("--followup", help="実装済みの作業ディレクトリ (カンマ区切り) に追加の依頼をする")
    parser.add_argument("--variant", help="upstream-<ケース>/variants/<名前>/ のファイルで plugin の同じパスを差し替えた写しを読み込む")
    args = parser.parse_args()
    args.plugin_dir = None
    if args.variant:
        # evals/ の下は plugin の条件から読めないので、写しは外に置く。/tmp/czr と /tmp/claude-501 は汚染の検査に当たるので避ける
        overlay = EVALS / f"upstream-{args.case}" / "variants" / args.variant
        args.plugin_dir = Path(tempfile.mkdtemp(prefix=f"{args.variant}-", dir="/private/tmp"))
        shutil.copytree(PLUGIN, args.plugin_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns("evals", ".claude"))
        shutil.copytree(overlay, args.plugin_dir, dirs_exist_ok=True)
    case = load_case(args.case)
    out_dir = EVALS / "results" / time.strftime(f"upstream-{case.slug}-%Y%m%d-%H%M%S-{os.getpid()}")
    out_dir.mkdir(parents=True)
    conditions = args.conditions.split(",")
    if set(conditions) - set(CONDITIONS):
        parser.error(f"--conditions は {CONDITIONS} から選ぶ")
    if args.branch and set(conditions) - set(BRANCH_SOURCE):
        parser.error(f"--branch で走らせられるのは {tuple(BRANCH_SOURCE)}")

    def record(labeled):
        label, job = labeled
        try:
            row = job()
        except Exception as exc:
            row = {"condition": label, "error": f"{type(exc).__name__}: {exc}", "cost_usd": None}
        with WRITE_LOCK, (out_dir / "results.jsonl").open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print({k: row.get(k) for k in ("condition", "workspace", "arm", "error", "hidden_rate", "followup_rate", "cost_usd", "seconds")}, file=sys.stderr, flush=True)
        return row

    with concurrent.futures.ThreadPoolExecutor(args.concurrency) as pool:
        if args.replay:
            sources = [Path(d) / f"{r['condition']}-{r['run']}" for d in args.replay.split(",") for r in good_runs(Path(d))]
            jobs = [(s.name, lambda s=s: replay(s, args, out_dir, case)) for s in sources if (s / "pre-impl").is_dir() for _ in range(args.runs)]
            list(pool.map(record, jobs))
        elif args.followup:
            jobs = [(f"{w}-{a}-{i}", lambda w=Path(w), a=a, i=i: followup(w, a, i, args, out_dir, case))
                    for i in range(args.runs) for w in args.followup.split(",") for a in ("docs", "stripped")]
            list(pool.map(record, jobs))
        elif args.branch:
            source = Path(args.branch)
            jobs = [(c, r["run"], source / f"{r['condition']}-{r['run']}") for c in conditions for r in good_runs(source) if r["condition"] == BRANCH_SOURCE[c]]
            print_table(list(pool.map(lambda job: run_one(job[0], job[1], args, out_dir, case, job[2]), jobs)))
        else:
            jobs = [(c, i) for i in range(args.runs) for c in conditions]
            print_table(list(pool.map(lambda job: run_one(*job, args, out_dir, case), jobs)))
    print(f"\n{out_dir}")


if __name__ == "__main__":
    main()
