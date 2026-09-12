#!/usr/bin/env python3
"""crystallize report-index — 複数プロジェクトの docs/crystallize/reports/ を一覧するローカルサーバー。

標準ライブラリのみ。127.0.0.1 にしか bind しない。

サブコマンド:
  serve    [--port N]                 フォアグラウンドでサーバーを起動する
  register --root <projroot>          プロジェクトを一覧の走査対象に登録する (ネットワーク不要)
  status                              起動中のサーバー (全ポート) の URL を出す
  ensure   --root <projroot> [--open] register + 未起動なら起動 + (--open で) ブラウザで一覧を開く
  stop                                起動中のサーバーを止める

設計メモ (sandbox 実測に基づく):
  Claude Code の sandbox 内の Bash では、ポートの bind・loopback への接続・ホーム配下への書き込みが
  いずれも "Operation not permitted" になる。そのため
  - 登録はファイル (registry dir) で行い、HTTP を使わない
  - 起動確認は state ファイル + サーバーが握る flock (server-<port>.lock) で行い、HTTP を使わない
    (lock は読み取り fd で試せるので sandbox 内からでも判定できる。pid の再利用にも騙されない)
  - サーバー本体の起動だけは sandbox の外が必要 → ensure は bind 失敗を検出して exit 3 で知らせる
  - registry / state の置き場は ~/.crystallize を第一候補、書けなければ /tmp/claude/crystallize、
    それも駄目なら $TMPDIR/crystallize に落とす (読むときは全候補を合算する)
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import html
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP = "crystallize-report-server"
VERSION = "0.1.0"
DEFAULT_PORT = int(os.environ.get("CRYSTALLIZE_REPORT_PORT", "47311"))
REPORTS_SUBDIR = Path("docs") / "crystallize" / "reports"
SCRIPT_DIR = Path(__file__).resolve().parent
STYLE_CSS = SCRIPT_DIR.parent.parent / "html-report" / "assets" / "style.css"

EXIT_SANDBOX = 3  # bind / 接続が sandbox に拒否された。sandbox の外で再実行が必要


# --------------------------------------------------------------------------- 置き場
def _state_dirs() -> list[Path]:
    """registry / state の候補ディレクトリ。先頭ほど恒久的。"""
    cands = [Path.home() / ".crystallize"]
    for p in ("/tmp/claude", "/private/tmp/claude"):
        if Path(p).is_dir():
            cands.append(Path(p) / "crystallize")
            break
    tmp = os.environ.get("TMPDIR")
    if tmp:
        cands.append(Path(tmp) / "crystallize")
    seen: list[Path] = []
    for c in cands:
        if c not in seen:
            seen.append(c)
    return seen


def _writable_dir(sub: str = "") -> Path | None:
    for d in _state_dirs():
        target = d / sub if sub else d
        try:
            target.mkdir(parents=True, exist_ok=True)
            probe = target / f".probe-{os.getpid()}"
            probe.write_text("")
            probe.unlink()
            return target
        except OSError:
            continue
    return None


def _root_key(root: Path) -> str:
    return hashlib.sha1(str(root).encode("utf-8")).hexdigest()[:12]


def register_root(root: Path) -> Path | None:
    root = root.resolve()
    d = _writable_dir("roots")
    if d is None:
        return None
    (d / _root_key(root)).write_text(str(root) + "\n", encoding="utf-8")
    return d


def load_roots() -> list[Path]:
    """全候補ディレクトリの登録を合算。存在しないパスは捨てる。"""
    roots: dict[str, Path] = {}
    for d in _state_dirs():
        rd = d / "roots"
        if not rd.is_dir():
            continue
        for f in sorted(rd.iterdir()):
            try:
                p = Path(f.read_text(encoding="utf-8").strip())
            except OSError:
                continue
            if p.is_absolute() and p.is_dir():
                roots[str(p)] = p
    return sorted(roots.values(), key=lambda p: p.name.lower())


def persist_roots(roots: list[Path]) -> None:
    """サーバー側 (sandbox 外) が恒久的な置き場へ登録を写す。失敗しても致命ではない。"""
    d = _writable_dir("roots")
    if d is None:
        return
    for r in roots:
        try:
            (d / _root_key(r)).write_text(str(r) + "\n", encoding="utf-8")
        except OSError:
            pass


def _state_files(port: int | None) -> list[Path]:
    """state ファイルの候補。port=None なら全ポート分を集める。"""
    out: list[Path] = []
    for d in _state_dirs():
        if port is not None:
            out.append(d / f"server-{port}.json")
        elif d.is_dir():
            out.extend(sorted(d.glob("server-*.json")))
    return out


_held_lock = None  # serve が生きている間だけ握るロック (GC で閉じないよう参照を保持)


def acquire_lock(port: int) -> bool:
    """このポートのサーバーであることの証明。プロセスが死ねば OS が自動で解放する
    (pid の再利用や SIGKILL 後の残骸に騙されないため、生存判定は pid ではなくこのロックで行う)。"""
    global _held_lock
    d = _writable_dir()
    if d is None:
        return True  # ロックを置けない環境では判定を諦めて起動を優先する
    f = open(d / f"server-{port}.lock", "a+")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return False
    _held_lock = f
    return True


def _lock_held_by_other(port: int) -> bool:
    """他プロセスがこのポートのロックを握っているか (どの候補ディレクトリのロックでも可)。"""
    for d in _state_dirs():
        lf = d / f"server-{port}.lock"
        if not lf.exists():
            continue
        try:
            f = open(lf, "rb")  # 読み取りで開く: sandbox はホーム配下の書き込みを拒むが flock の確認は読み取り fd で足りる
        except OSError:
            continue
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError:
            f.close()
            return True
        f.close()
    return False


def write_state(port: int) -> None:
    payload = json.dumps(
        {"app": APP, "version": VERSION, "pid": os.getpid(), "port": port, "started": time.time()}
    )
    for f in _state_files(port):
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(payload, encoding="utf-8")
        except OSError:
            continue


def clear_state(port: int) -> None:
    for f in _state_files(port):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("pid") == os.getpid():
                f.unlink()
        except (OSError, ValueError):
            continue


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def read_state(port: int | None = None) -> dict | None:
    """生存しているサーバーの state を返す。port=None なら最も新しいもの。
    生存の根拠は flock (pid の再利用に強い)。ロックが置けなかった環境だけ pid で代用する。"""
    newest: dict | None = None
    for f in _state_files(port):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        pid = data.get("pid")
        p = data.get("port")
        if data.get("app") != APP or not isinstance(pid, int) or pid <= 0 or not isinstance(p, int):
            continue
        if not _lock_held_by_other(p) and not (_lock_missing(p) and _pid_alive(pid)):
            continue
        if newest is None or data.get("started", 0) > newest.get("started", 0):
            newest = data
    return newest


def _lock_missing(port: int) -> bool:
    return not any((d / f"server-{port}.lock").exists() for d in _state_dirs())


def log_path() -> Path | None:
    d = _writable_dir()
    return None if d is None else d / "server.log"


# --------------------------------------------------------------------------- 走査
_FNAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.html$")
_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
_LEDE_RE = re.compile(r'<p class="lede">(.*?)</p>', re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")

_cache: dict[str, tuple[float, dict]] = {}


def _strip(s: str) -> str:
    return html.unescape(_TAG_RE.sub("", s)).strip()


def scan_report(path: Path) -> dict:
    st = path.stat()
    cached = _cache.get(str(path))
    if cached and cached[0] == st.st_mtime:
        return cached[1]
    m = _FNAME_RE.match(path.name)
    date = m.group(1) if m else time.strftime("%Y-%m-%d", time.localtime(st.st_mtime))
    slug = m.group(2) if m else path.stem
    title = slug
    lede = ""
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:65536]
        tm = _TITLE_RE.search(head)
        if tm and _strip(tm.group(1)):
            title = _strip(tm.group(1))
        lm = _LEDE_RE.search(head)
        if lm:
            lede = _strip(lm.group(1))
    except OSError:
        pass
    kind = "diff-review" if slug.startswith("diff-review-") else "report"
    info = {
        "file": path.name,
        "date": date,
        "mtime": st.st_mtime,
        "title": title,
        "lede": lede,
        "kind": kind,
    }
    _cache[str(path)] = (st.st_mtime, info)
    return info


def scan_all() -> list[dict]:
    projects = []
    for root in load_roots():
        rdir = root / REPORTS_SUBDIR
        reports = []
        if rdir.is_dir():
            real_dir = rdir.resolve()
            for f in rdir.iterdir():
                if not (f.is_file() and f.suffix == ".html" and not f.name.startswith(".")):
                    continue
                try:
                    if f.resolve().parent != real_dir:
                        continue  # 外を指す symlink は配信もしないので一覧にも出さない
                    reports.append(scan_report(f))
                except OSError:
                    continue  # 走査中に消えた (レポートは作り直されることがある)
        reports.sort(key=lambda r: (r["date"], r["mtime"]), reverse=True)
        projects.append({"root": root, "key": _root_key(root), "reports": reports, "has_dir": rdir.is_dir()})
    return projects


# --------------------------------------------------------------------------- 描画
INDEX_CSS = """
/* report-index 固有 (一覧行)。トークンは style.css のものだけを使う */
.rx-head { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; margin-bottom: 1.2em; }
.rx-head h1 { margin: 0; }
.rx-count { color: var(--muted); font-family: var(--sans); font-size: .9em; }
.rx-tools { display: flex; gap: 10px; flex-wrap: wrap; margin: 0 0 1.6em; }
.rx-tools input, .rx-tools select {
  font: inherit; font-family: var(--sans); font-size: .92em;
  padding: 6px 10px; border: 1px solid var(--hairline-strong); border-radius: var(--radius-md);
  background: var(--surface-card); color: var(--ink); min-width: 220px;
}
.rx-tools input { min-width: 320px; flex: 1 1 320px; max-width: 520px; }
.rx-tools input:focus, .rx-tools select:focus { outline: 2px solid var(--primary); outline-offset: 1px; }
.rx-project { margin: 0 0 2em; }
.rx-project h2 { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.rx-project h2 .src { font-weight: 400; }
/* カードは style.css の .cards / .card をそのまま使い、中身の並びだけここで決める */
.rx-card { display: flex; flex-direction: column; gap: 8px; position: relative; transition: border-color .12s ease; }
.rx-card:hover { border-color: var(--primary); }
.rx-card-meta { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.rx-date { font-family: var(--mono); font-size: .82em; color: var(--muted); white-space: nowrap; }
.rx-title { margin: 0; font-size: 1.02em; line-height: 1.4; }
.rx-title a { color: var(--ink); text-decoration: none; font-weight: 600; }
.rx-title a::after { content: ""; position: absolute; inset: 0; }  /* カード全体をクリック可能に */
.rx-card:hover .rx-title a { color: var(--primary); }
.rx-lede { color: var(--muted); font-size: .9em; margin: 0; line-height: 1.55;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.rx-empty { color: var(--muted); padding: 10px 6px; }
.rx-hidden { display: none; }
"""

INDEX_JS = """
(function () {
  var root = document.documentElement;
  var KEY = 'crystallize-report-theme';
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) { saved = null; }
  var prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  root.dataset.theme = (saved === 'dark' || saved === 'light') ? saved : (prefersDark ? 'dark' : 'light');
  var btn = document.getElementById('themeToggle');
  if (btn) {
    btn.addEventListener('click', function () {
      var next = root.dataset.theme === 'dark' ? 'light' : 'dark';
      root.dataset.theme = next;
      try { localStorage.setItem(KEY, next); } catch (e) {}
    });
  }
  var q = document.getElementById('rxQuery');
  var sel = document.getElementById('rxProject');
  var kind = document.getElementById('rxKind');
  function apply() {
    var needle = (q.value || '').toLowerCase();
    var proj = sel.value;
    var kd = kind.value;
    var shown = 0;
    document.querySelectorAll('.rx-project').forEach(function (sec) {
      var visibleRows = 0;
      var projOk = !proj || sec.dataset.key === proj;
      sec.querySelectorAll('.rx-card').forEach(function (row) {
        var ok = projOk
          && (!kd || row.dataset.kind === kd)
          && (!needle || (row.textContent + ' ' + (row.dataset.file || '')).toLowerCase().indexOf(needle) >= 0);
        row.classList.toggle('rx-hidden', !ok);
        if (ok) visibleRows++;
      });
      sec.classList.toggle('rx-hidden', !projOk || (visibleRows === 0 && (needle || kd)));
      shown += visibleRows;
    });
    var c = document.getElementById('rxShown');
    if (c) c.textContent = shown;
  }
  [q, sel, kind].forEach(function (el) { el.addEventListener('input', apply); });
  apply();
})();
"""


def _load_style() -> str:
    try:
        return STYLE_CSS.read_text(encoding="utf-8")
    except OSError:
        return (
            ":root{--canvas:#f6f5f4;--canvas-soft:#faf9f8;--surface-card:#fff;--surface-strong:#e9e7e4;"
            "--ink:#141413;--body:#31302e;--muted:#615d59;--hairline:#e6e6e6;--hairline-soft:#efeeec;"
            "--hairline-strong:#d3d1ce;--primary:#006bca;--primary-active:#005bab;--primary-tint:#e9f2fb;"
            "--radius-md:8px;--sans:-apple-system,BlinkMacSystemFont,sans-serif;--mono:ui-monospace,monospace}"
            "body{margin:0;background:var(--canvas);color:var(--body);font-family:var(--sans)}"
            ".report{max-width:1400px;margin:0 auto;padding:40px 32px 96px}"
            ".badge{display:inline-block;padding:1px 8px;border-radius:9999px;background:var(--primary-tint);"
            "color:var(--primary-active);border:1px solid var(--primary);font-size:.72em;font-weight:600}"
            ".badge.plain{background:var(--surface-strong);color:var(--muted);border-color:var(--hairline-strong)}"
            ".src{margin-left:.5em;color:var(--muted);font-family:var(--mono);font-size:.82em}"
            ".theme-toggle{position:fixed;top:14px;right:18px}"
        )


def render_index(projects: list[dict]) -> str:
    e = html.escape
    total = sum(len(p["reports"]) for p in projects)
    parts: list[str] = []
    parts.append(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>crystallize レポート一覧</title>"
        f"<style>{_load_style()}\n{INDEX_CSS}</style></head><body>"
        '<button class="theme-toggle" id="themeToggle" type="button" aria-label="テーマ切り替え">◐</button>'
        '<main class="report markdown-body">'
        '<div class="rx-head"><h1>crystallize レポート一覧</h1>'
        f'<span class="rx-count">表示 <span id="rxShown">{total}</span> / 全 {total} 件 · '
        f"{len(projects)} プロジェクト</span></div>"
    )
    parts.append(
        '<div class="rx-tools">'
        '<input id="rxQuery" type="search" placeholder="題名・要約・ファイル名で絞り込む" aria-label="絞り込み">'
        '<select id="rxProject" aria-label="プロジェクト"><option value="">すべてのプロジェクト</option>'
        + "".join(f'<option value="{p["key"]}">{e(p["root"].name)}</option>' for p in projects)
        + "</select>"
        '<select id="rxKind" aria-label="種別"><option value="">すべての種別</option>'
        '<option value="report">レポート</option><option value="diff-review">diff-review</option></select>'
        "</div>"
    )
    if not projects:
        parts.append(
            '<p class="note">登録されたプロジェクトがありません。各プロジェクトで html-report か diff-review を'
            " 1 回実行するか、<code>report_server.py register --root &lt;projroot&gt;</code> を実行してください。</p>"
        )
    for p in projects:
        parts.append(
            f'<section class="rx-project" data-key="{p["key"]}">'
            f'<h2>{e(p["root"].name)} <span class="src">{e(str(p["root"]))}</span></h2>'
        )
        if not p["reports"]:
            msg = "レポートはまだありません" if p["has_dir"] else "docs/crystallize/reports/ がありません"
            parts.append(f'<p class="rx-empty">{msg}</p></section>')
            continue
        parts.append('<div class="cards">')
        for r in p["reports"]:
            href = f'/r/{p["key"]}/{urllib.parse.quote(r["file"])}'
            badge = (
                '<span class="badge plain">diff-review</span>'
                if r["kind"] == "diff-review"
                else '<span class="badge">レポート</span>'
            )
            lede = f'<p class="rx-lede" title="{e(r["lede"])}">{e(r["lede"])}</p>' if r["lede"] else ""
            parts.append(
                f'<article class="card rx-card" data-kind="{r["kind"]}" data-file="{e(r["file"])}">'
                f'<div class="rx-card-meta">{badge}<span class="rx-date">{e(r["date"])}</span></div>'
                f'<h3 class="rx-title"><a href="{href}" target="_blank" rel="noopener" title="{e(r["file"])}">'
                f'{e(r["title"])}</a></h3>{lede}</article>'
            )
        parts.append("</div></section>")
    parts.append(
        f'<p class="note">{APP} v{VERSION} · 登録の追加: <code>report_server.py register --root &lt;projroot&gt;</code></p>'
        f"</main><script>{INDEX_JS}</script></body></html>"
    )
    return "".join(parts)


# --------------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = f"{APP}/{VERSION}"

    def log_message(self, fmt, *args):  # 静かに
        pass

    def _send(self, status: int, body: bytes, ctype: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            self._route()
        except Exception as ex:  # 1 リクエストの例外で接続を落とさない
            try:
                self._send(500, f"internal error: {type(ex).__name__}".encode("utf-8"), "text/plain; charset=utf-8")
            except Exception:
                pass

    def _route(self):
        # DNS rebinding 対策: loopback 以外の Host を名乗る要求は受けない
        host = (self.headers.get("Host") or "").strip().lower()
        hostname = host[1:].split("]")[0] if host.startswith("[") else host.split(":")[0]
        if hostname not in ("127.0.0.1", "localhost", "::1"):
            self._send(403, b"forbidden host", "text/plain; charset=utf-8")
            return
        path = urllib.parse.urlsplit(self.path).path
        if path == "/" or path == "/index.html":
            projects = scan_all()
            self._send(200, render_index(projects).encode("utf-8"))
            return
        if path == "/healthz":
            body = json.dumps({"app": APP, "version": VERSION, "pid": os.getpid()}).encode("utf-8")
            self._send(200, body, "application/json")
            return
        m = re.match(r"^/r/([0-9a-f]{12})/([^/]+)$", path)
        if m:
            self._serve_report(m.group(1), urllib.parse.unquote(m.group(2)))
            return
        self._send(404, b"not found", "text/plain; charset=utf-8")

    def _serve_report(self, key: str, name: str) -> None:
        root = next((r for r in load_roots() if _root_key(r) == key), None)
        if root is None:
            self._send(404, b"unknown project", "text/plain; charset=utf-8")
            return
        # basename のみ・.html のみ・reports ディレクトリの直下のみ
        if "/" in name or "\\" in name or "\x00" in name or name.startswith(".") or not name.endswith(".html"):
            self._send(403, b"forbidden", "text/plain; charset=utf-8")
            return
        rdir = (root / REPORTS_SUBDIR).resolve()
        target = (rdir / name).resolve()
        if target.parent != rdir or not target.is_file():
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        try:
            self._send(200, target.read_bytes())
        except OSError:
            self._send(500, b"read error", "text/plain; charset=utf-8")


def cmd_serve(port: int) -> int:
    if not acquire_lock(port):
        print(f"ポート {port} の {APP} は既に起動しています。", file=sys.stderr)
        return 4
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except PermissionError as ex:
        print(f"bind 127.0.0.1:{port} が拒否されました ({ex}). sandbox の外で起動してください。", file=sys.stderr)
        return EXIT_SANDBOX
    except OSError as ex:
        print(f"bind 127.0.0.1:{port} に失敗しました: {ex}", file=sys.stderr)
        return 2
    srv.daemon_threads = True
    write_state(port)
    persist_roots(load_roots())

    def _term(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _term)
    print(f"{APP} v{VERSION} http://127.0.0.1:{port}/", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        clear_state(port)
        srv.server_close()
    return 0


def _spawn_server(port: int) -> subprocess.Popen:
    """サーバーを切り離して起動する。返した Popen の returncode で起動失敗の種類が分かる。"""
    lp = log_path()
    out = open(lp, "ab") if lp else subprocess.DEVNULL
    return subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "serve", "--port", str(port)],
        stdin=subprocess.DEVNULL,
        stdout=out,
        stderr=out,
        start_new_session=True,
        close_fds=True,
    )


def _wait_state(port: int, proc: subprocess.Popen, timeout: float = 5.0) -> dict | int | None:
    """state が現れれば dict、子が先に死ねばその returncode、時間切れなら None。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = read_state(port)
        if st and st.get("version") == VERSION:
            return st
        rc = proc.poll()
        if rc is not None:
            return rc
        time.sleep(0.15)
    return None


def _url(port: int) -> str:
    return f"http://127.0.0.1:{port}/"


def cmd_ensure(root: Path | None, port: int, do_open: bool) -> int:
    if root is not None:
        if not root.is_dir():
            print(f"--root が存在しません: {root}", file=sys.stderr)
            return 2
        where = register_root(root)
        if where is None:
            print("登録先に書き込めませんでした (ホーム・/tmp/claude・$TMPDIR すべて不可)。", file=sys.stderr)

    st = read_state(port)
    if st and st.get("version") != VERSION:
        # プラグイン更新後に古いサーバーが残っている。止めて起動し直す (止められなければ失敗として返す)
        old_pid = int(st["pid"])
        try:
            os.kill(old_pid, signal.SIGTERM)
        except OSError as ex:
            print(
                f"旧バージョン ({st.get('version')}) のサーバー pid={old_pid} を止められませんでした: {ex}. "
                "sandbox の外で `stop` を実行してください。",
                file=sys.stderr,
            )
            return 2
        deadline = time.time() + 3.0
        while time.time() < deadline and _lock_held_by_other(port):
            time.sleep(0.1)
        st = None
    if st is None:
        proc = _spawn_server(port)
        res = _wait_state(port, proc)
        if not isinstance(res, dict):
            lp = log_path()
            hint = f" ログ: {lp}" if lp else ""
            me = Path(__file__).resolve()
            if res == EXIT_SANDBOX:
                print(
                    f"サーバーを起動できませんでした (sandbox がポート bind を拒否).{hint}\n"
                    "同じコマンドを sandbox を無効にして 1 回だけ再実行するか、ターミナルから\n"
                    f"  ! nohup python3 {me} serve >/dev/null 2>&1 &\n"
                    "で起動してください。",
                    file=sys.stderr,
                )
                return EXIT_SANDBOX
            if res == 2:
                print(
                    f"ポート {port} は別のプロセスが使っています。--port <番号> か CRYSTALLIZE_REPORT_PORT で変えてください.{hint}",
                    file=sys.stderr,
                )
                return 2
            print(f"サーバーを起動できませんでした (exit={res}).{hint}", file=sys.stderr)
            return 2
        st = res
    url = _url(int(st.get("port", port)))
    print(url)
    print(f"projects={len(load_roots())}")
    if do_open:
        try:
            subprocess.run(["open", url], check=False, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
    return 0


def _running_states() -> list[dict]:
    seen: dict[int, dict] = {}
    for f in _state_files(None):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        p = data.get("port")
        if isinstance(p, int) and p not in seen:
            st = read_state(p)
            if st:
                seen[p] = st
    return list(seen.values())


def cmd_status() -> int:
    states = _running_states()
    if not states:
        print("not running")
        return 1
    for st in states:
        print(f"running pid={st['pid']} v{st.get('version')} {_url(int(st['port']))}")
    return 0


def cmd_stop() -> int:
    states = _running_states()
    if not states:
        print("not running")
        return 0
    rc = 0
    for st in states:
        try:
            os.kill(int(st["pid"]), signal.SIGTERM)
            print(f"stopped pid={st['pid']} port={st['port']}")
        except OSError as ex:
            print(f"停止できませんでした (pid={st['pid']}): {ex}", file=sys.stderr)
            rc = EXIT_SANDBOX if isinstance(ex, PermissionError) else 2
    return rc


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="report_server.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=DEFAULT_PORT)
    r = sub.add_parser("register")
    r.add_argument("--root", required=True)
    sub.add_parser("status")
    en = sub.add_parser("ensure")
    en.add_argument("--root")
    en.add_argument("--port", type=int, default=DEFAULT_PORT)
    en.add_argument("--open", action="store_true")
    sub.add_parser("stop")
    a = ap.parse_args(argv)

    if a.cmd == "serve":
        return cmd_serve(a.port)
    if a.cmd == "register":
        where = register_root(Path(a.root))
        if where is None:
            print("登録先に書き込めませんでした。", file=sys.stderr)
            return 2
        print(f"registered {Path(a.root).resolve()} -> {where}")
        return 0
    if a.cmd == "status":
        return cmd_status()
    if a.cmd == "ensure":
        return cmd_ensure(Path(a.root) if a.root else None, a.port, a.open)
    if a.cmd == "stop":
        return cmd_stop()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
