"""Characterization tests for the original Markdown-backed Study Loop UI behavior."""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
SERVER_PATH = SCRIPTS / "server.py"
sys.path.insert(0, str(SERVER_PATH.parent))
SPEC = importlib.util.spec_from_file_location("study_loop_server", SERVER_PATH)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


LESSON = """# Lesson 1: Characterization
Level 1 / Remember / recall / Stage 1

## 課題

説明してください。

## 回答欄

<!-- ここに記入してください -->


---

## ヒント

ヒントです。

---

## 採点

_未採点_

## 解説

_未採点_
"""


class MarkdownCharacterizationTests(unittest.TestCase):
    def test_extract_answer_ignores_template_comment_and_hints(self) -> None:
        self.assertEqual(server.extract_answer(LESSON), "")

    def test_replace_answer_keeps_surrounding_markdown(self) -> None:
        replaced = server.replace_answer(LESSON, "回答本文")

        self.assertIn("<!-- 提出済み:", replaced)
        self.assertIn("回答本文", replaced)
        self.assertIn("## ヒント\n\nヒントです。", replaced)
        self.assertIn("## 採点\n\n_未採点_", replaced)
        self.assertEqual(server.extract_answer(replaced), "回答本文")

    def test_multipart_code_answer_round_trip_preserves_real_newlines_indentation_and_backslashes(self) -> None:
        answer = """### Part B
<!-- study-answer top="part-b" sub="q1" -->
```python
  pattern = r"\\1"
  print(pattern)
```
<!-- /study-answer -->

<!-- study-answer top="part-b" sub="q2" -->
    indented = r"C:\\work\\code"
<!-- /study-answer -->"""
        source = f"# Lesson\n\n## 回答欄\n\n{answer}\n\n---\n\n## 採点\n\n_未採点_\n"

        stored = server.replace_answer(source, answer)
        extracted = server.extract_answer(stored)
        parts, trailing = server.split_answer_parts(extracted)

        self.assertEqual(parts["part-b"]["q1"], "```python\n  pattern = r\"\\1\"\n  print(pattern)\n```")
        self.assertEqual(parts["part-b"]["q2"], "    indented = r\"C:\\work\\code\"")
        self.assertEqual(trailing, "")
        app_js = (SCRIPTS / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("form.requestSubmit()", app_js)
        self.assertNotIn("form.submit()", app_js)
        lesson_template = (SCRIPTS / "templates" / "lesson.html").read_text(encoding="utf-8")
        self.assertIn('top-heading="${encodeURIComponent(group.heading)}"', lesson_template)
        self.assertIn('sub-heading="${encodeURIComponent(i.subHeading)}"', lesson_template)

    def test_legacy_answer_without_slot_markers_is_restored(self) -> None:
        parts, trailing = server.split_answer_parts(
            "### Part A\n\n以前の回答\n\n### Part B\n\n#### Q1\n\n二つ目の回答"
        )

        self.assertEqual(parts["part-a"]["_flat"], "以前の回答")
        self.assertEqual(parts["part-b"]["q1"], "二つ目の回答")
        self.assertEqual(trailing, "")

    def test_legacy_answer_without_heading_maps_to_the_single_task(self) -> None:
        parts, trailing = server.split_answer_parts("見出しのない既存回答")

        self.assertEqual(parts["main"]["_flat"], "見出しのない既存回答")
        self.assertEqual(trailing, "")

    def test_multipart_serializer_round_trip_preserves_literal_delimiter_lines(self) -> None:
        end_marker = "<!-- /study-answer -->"

        def serialize_slot(value: str) -> str:
            # This is the form serializer contract: backslashes are escaped
            # first, then literal end delimiters become an unambiguous token.
            return value.replace("\\", "\\\\").replace(end_marker, "\\M")

        first = f"before\n{end_marker}\nafter\n{end_marker}"
        second = r"literal \M and C:\\work\\code"
        answer = (
            "### Part B\n\n"
            f'<!-- study-answer top="part-b" sub="q1" -->\n{serialize_slot(first)}\n{end_marker}\n\n'
            f'<!-- study-answer top="part-b" sub="q2" -->\n{serialize_slot(second)}\n{end_marker}'
        )
        source = f"# Lesson\n\n## 回答欄\n\n{answer}\n\n---\n\n## 採点\n\n_未採点_\n"

        parts, trailing = server.split_answer_parts(server.extract_answer(server.replace_answer(source, answer)))

        self.assertEqual(parts["part-b"]["q1"], first)
        self.assertEqual(parts["part-b"]["q2"], second)
        self.assertEqual(trailing, "")
        lesson_template = (SCRIPTS / "templates" / "lesson.html").read_text(encoding="utf-8")
        self.assertIn("const escapeSlotContent", lesson_template)
        self.assertIn("escapeSlotContent(i.text)", lesson_template)

    def test_code_fenced_task_uses_the_code_answer_style(self) -> None:
        parts = server.split_body_parts(
            """## 課題

### Part A

次の関数を完成させてください。

```typescript
function greet(name: string) {
  // implement
}
```
"""
        )

        self.assertEqual(parts[0]["answer_style"], "code")

    def test_score_feedback_maps_to_three_visible_states(self) -> None:
        self.assertEqual(server.score_feedback("0.84")["mark"], "○")
        self.assertEqual(server.score_feedback("0.72")["mark"], "△")
        self.assertEqual(server.score_feedback("0.30")["mark"], "×")


class SubmissionCharacterizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / ".study"
        self.lesson = self.root / "python" / "lessons" / "001-characterization.md"
        self.lesson.parent.mkdir(parents=True)
        self.lesson.write_text(LESSON, encoding="utf-8")
        server.app.config.update(TESTING=True, ROOT=self.root)
        self.client = server.app.test_client()
        with self.client.session_transaction() as session:
            session["csrf_token"] = "test-csrf"

    def test_submit_persists_answer_then_redirects_to_confirmation(self) -> None:
        response = self.client.post(
            "/python/lessons/001-characterization.md/submit",
            data={"answer": "提出した回答", "csrf_token": "test-csrf"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/python/lessons/001-characterization.md/confirmation?token=", response.headers["Location"])
        saved = self.lesson.read_text(encoding="utf-8")
        self.assertEqual(server.extract_answer(saved), "提出した回答")

    def test_headingless_legacy_answer_is_rendered_in_the_single_task(self) -> None:
        self.lesson.write_text(
            server.replace_answer(LESSON, "見出しのない既存回答"),
            encoding="utf-8",
        )

        response = self.client.get("/python/lessons/001-characterization.md")

        self.assertEqual(response.status_code, 200)
        self.assertIn(">見出しのない既存回答</textarea>", response.get_data(as_text=True))

    def test_each_task_renders_its_matching_hint_inside_the_task(self) -> None:
        self.lesson.write_text(
            """# Lesson 1: Inline hints

## 課題

### Part B: コード

コードを書いてください。

### Part C: 説明

理由を説明してください。

## 回答欄

---

## ヒント

<details><summary>ヒント1: 着眼点</summary>

- Part B: 配列の変換方法を確認します。
- Part C: 同じ項目の識別方法を考えます。

</details>

---

## 採点

_未採点_
""",
            encoding="utf-8",
        )

        response = self.client.get("/python/lessons/001-characterization.md")
        html = response.get_data(as_text=True)
        task_one = html.split('data-task-id="1"', 1)[1].split('data-task-id="2"', 1)[0]
        task_two = html.split('data-task-id="2"', 1)[1].split("</section>", 1)[0]

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('class="lesson-hints"', html)
        self.assertIn('class="inline-hint"', task_one)
        self.assertIn("配列の変換方法を確認します。", task_one)
        self.assertNotIn("同じ項目の識別方法を考えます。", task_one)
        self.assertIn('class="inline-hint"', task_two)
        self.assertIn("同じ項目の識別方法を考えます。", task_two)

    def test_hint_text_outside_details_remains_available_to_each_task(self) -> None:
        self.lesson.write_text(
            """# Lesson 1: Hint supplement

## 課題

### Part B

コードを書いてください。

### Part C

理由を説明してください。

## 回答欄

---

## ヒント

どちらの課題でも、前の解説を読み直してください。

<details open><summary>ヒント1: Part B</summary>

Part Bだけの補足です。

</details>

---

## 採点

_未採点_
""",
            encoding="utf-8",
        )

        html = self.client.get("/python/lessons/001-characterization.md").get_data(as_text=True)
        task_one = html.split('data-task-id="1"', 1)[1].split('data-task-id="2"', 1)[0]
        task_two = html.split('data-task-id="2"', 1)[1].split("</section>", 1)[0]

        self.assertIn("どちらの課題でも、前の解説を読み直してください。", task_one)
        self.assertIn("どちらの課題でも、前の解説を読み直してください。", task_two)
        self.assertIn("Part Bだけの補足です。", task_one)
        self.assertNotIn("Part Bだけの補足です。", task_two)

    def test_part_name_inside_hint_code_does_not_change_the_target_task(self) -> None:
        self.lesson.write_text(
            """# Lesson 1: Hint code

## 課題

### Part B

コードを書いてください。

### Part C

理由を説明してください。

## 回答欄

---

## ヒント

<details><summary>ヒント1: Part B</summary>

```ts
console.log("Part C");
```

</details>

---

## 採点

_未採点_
""",
            encoding="utf-8",
        )

        html = self.client.get("/python/lessons/001-characterization.md").get_data(as_text=True)
        task_one = html.split('data-task-id="1"', 1)[1].split('data-task-id="2"', 1)[0]
        task_two = html.split('data-task-id="2"', 1)[1].split("</section>", 1)[0]

        self.assertIn("console.log(&quot;Part C&quot;);", task_one)
        self.assertNotIn("console.log(&quot;Part C&quot;);", task_two)

    def test_hint_blocks_keep_their_original_order(self) -> None:
        self.lesson.write_text(
            """# Lesson 1: Hint order

## 課題

### Part B

コードを書いてください。

## 回答欄

---

## ヒント

<details><summary>最初のヒント</summary>

先に確認する内容です。

</details>

最後に確認する補足です。

---

## 採点

_未採点_
""",
            encoding="utf-8",
        )

        html = self.client.get("/python/lessons/001-characterization.md").get_data(as_text=True)
        task = html.split('data-task-id="1"', 1)[1].split("</section>", 1)[0]

        self.assertLess(task.index("先に確認する内容です。"), task.index("最後に確認する補足です。"))

    def test_longer_hint_code_fence_is_not_closed_by_a_shorter_fence(self) -> None:
        self.lesson.write_text(
            """# Lesson 1: Hint fence

## 課題

### Part B

コードを書いてください。

### Part C

理由を説明してください。

## 回答欄

---

## ヒント

<details><summary>ヒント1: Part B</summary>

````md
```ts
Part C: これはコード例です。
```
````

</details>

---

## 採点

_未採点_
""",
            encoding="utf-8",
        )

        html = self.client.get("/python/lessons/001-characterization.md").get_data(as_text=True)
        task_one = html.split('data-task-id="1"', 1)[1].split('data-task-id="2"', 1)[0]
        task_two = html.split('data-task-id="2"', 1)[1].split("</section>", 1)[0]

        self.assertIn("これはコード例です。", task_one)
        self.assertNotIn("これはコード例です。", task_two)

    def test_indented_fence_inside_hint_code_does_not_end_the_outer_fence(self) -> None:
        self.lesson.write_text(
            """# Lesson 1: Indented hint fence

## 課題

### Part B

コードを書いてください。

### Part C

理由を説明してください。

## 回答欄

---

## ヒント

<details><summary>ヒント1: Part B</summary>

````md
    ````
Part C: これはコード例です。
````

</details>

---

## 採点

_未採点_
""",
            encoding="utf-8",
        )

        html = self.client.get("/python/lessons/001-characterization.md").get_data(as_text=True)
        task_one = html.split('data-task-id="1"', 1)[1].split('data-task-id="2"', 1)[0]
        task_two = html.split('data-task-id="2"', 1)[1].split("</section>", 1)[0]

        self.assertIn("これはコード例です。", task_one)
        self.assertNotIn("これはコード例です。", task_two)

    def test_hint_for_read_only_part_is_not_repeated_on_answer_tasks(self) -> None:
        self.lesson.write_text(
            """# Lesson 1: Read-only hint

## 課題

### Part A: 読むだけ

次の説明を読んでください。

### Part B

コードを書いてください。

### Part C

理由を説明してください。

## 回答欄

---

## ヒント

<details><summary>ヒント1: Part A</summary>

読む部分だけの補足です。

</details>

---

## 採点

_未採点_
""",
            encoding="utf-8",
        )

        html = self.client.get("/python/lessons/001-characterization.md").get_data(as_text=True)

        self.assertNotIn("読む部分だけの補足です。", html)


class CsrfTemplateContractTests(unittest.TestCase):
    """Browser forms must receive the session token, not Jinja's function repr."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name) / ".study"
        root.mkdir()
        server.app.config.update(TESTING=True, ROOT=root, BACKEND="manual")
        self.client = server.app.test_client()

    def test_new_learning_renders_the_real_session_csrf_token(self) -> None:
        response = self.client.get("/new")
        html = response.get_data(as_text=True)
        with self.client.session_transaction() as session:
            token = session["csrf_token"]

        self.assertEqual(response.status_code, 200)
        self.assertIn(f'content="{token}"', html)
        self.assertIn(f'value="{token}"', html)
        self.assertNotIn("function csrf_token", html)

    def test_setup_accepts_the_token_emitted_by_new_learning(self) -> None:
        html = self.client.get("/new").get_data(as_text=True)
        match = re.search(r'<meta name="csrf-token" content="([^"]+)">', html)
        self.assertIsNotNone(match)
        token = match.group(1) if match else ""

        response = self.client.post(
            "/setup",
            data={
                "csrf_token": token,
                "topic": "CSRF contract",
                "why": "ブラウザ投稿を確認する",
                "success_criteria": "トークンを送信できる\nCSRF を検証できる",
                "constraints": "なし",
                "out_of_scope": "なし",
                "retention_interval": "1週間",
                "target_level": "3",
                "time_budget": "30分",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/setup/confirm", response.headers["Location"])


class NavigationInformationArchitectureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / ".study"
        topic = self.root / "python"
        lessons = topic / "lessons"
        lessons.mkdir(parents=True)
        (topic / "README.md").write_text(
            """# Study Loop: Python

**Last updated**: 2026-07-24
**Current Level**: 2
**Target Level**: 4
**Stage**: 1
**Ended**: -

## Mission

### Success looks like

- 小さなプログラムを自力で書ける

## Progress

- Stage 1 (Foundation): 1 / 3
""",
            encoding="utf-8",
        )
        (lessons / "001.md").write_text(
            "# Lesson 001: 変数\n\n## 採点\n\n**Score**: 0.84\n",
            encoding="utf-8",
        )
        (lessons / "002.md").write_text(
            "# Lesson 002: 条件分岐\n\n## 採点\n\n_未採点_\n",
            encoding="utf-8",
        )
        (topic / "curriculum.md").write_text(
            "# Curriculum\n\n## Stage 1\n\n基礎を学びます。\n",
            encoding="utf-8",
        )
        (topic / "GLOSSARY.md").write_text(
            "# Glossary\n\n## 変数\n\n値を保持する名前です。\n",
            encoding="utf-8",
        )
        server.app.config.update(TESTING=True, ROOT=self.root, BACKEND="manual")
        self.client = server.app.test_client()

    def test_home_resumes_the_first_ungraded_lesson(self) -> None:
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/python/lessons/002.md"', html)
        self.assertIn("続きから始める", html)
        self.assertIn("Lesson 002: 条件分岐", html)
        self.assertIn("小さなプログラムを自力で書ける", html)
        self.assertIn("1 / 3", html)

    def test_learning_library_lists_courses_and_lessons(self) -> None:
        response = self.client.get("/learning")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("学習一覧", html)
        self.assertIn("Python", html)
        self.assertIn("Lesson 001: 変数", html)
        self.assertIn("Lesson 002: 条件分岐", html)
        self.assertIn('data-start-action="spaced_review"', html)
        self.assertIn('data-start-action="session_end"', html)

    def test_topic_dashboard_redirects_to_the_learning_library(self) -> None:
        response = self.client.get("/python/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/learning?topic=python", response.headers["Location"])

    def test_mobile_lesson_drawer_has_a_close_control_inside_the_sidebar(self) -> None:
        response = self.client.get("/python/lessons/002.md")
        html = response.get_data(as_text=True)
        sidebar = html.split('<aside class="lesson-sidebar"', 1)[1].split("</aside>", 1)[0]

        self.assertEqual(response.status_code, 200)
        self.assertIn('data-sidebar-close', sidebar)
        self.assertIn('aria-label="レッスン一覧を閉じる"', sidebar)

    def test_curriculum_opened_from_a_lesson_returns_to_that_lesson(self) -> None:
        lesson_html = self.client.get("/python/lessons/002.md").get_data(as_text=True)

        self.assertIn(
            'href="/python/curriculum?return_to=/python/lessons/002.md"',
            lesson_html,
        )

        response = self.client.get(
            "/python/curriculum",
            query_string={"return_to": "/python/lessons/002.md"},
        )
        html = response.get_data(as_text=True)
        header = html.split('<header class="topbar">', 1)[1].split("</header>", 1)[0]

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/python/lessons/002.md"', header)
        self.assertIn("カリキュラム", header)
        self.assertNotIn(">ホーム<", header)
        self.assertNotIn(">学習一覧<", header)
        self.assertNotIn("新しい学習", header)

    def test_glossary_opened_from_a_lesson_returns_to_that_lesson(self) -> None:
        lesson_html = self.client.get("/python/lessons/002.md").get_data(as_text=True)

        self.assertIn(
            'href="/python/glossary?return_to=/python/lessons/002.md"',
            lesson_html,
        )

        response = self.client.get(
            "/python/glossary",
            query_string={"return_to": "/python/lessons/002.md"},
        )
        html = response.get_data(as_text=True)
        header = html.split('<header class="topbar">', 1)[1].split("</header>", 1)[0]

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/python/lessons/002.md"', header)
        self.assertIn("用語集", header)
        self.assertNotIn(">ホーム<", header)
        self.assertNotIn(">学習一覧<", header)
        self.assertNotIn("新しい学習", header)

    def test_missing_lesson_return_target_falls_back_to_the_learning_library(self) -> None:
        response = self.client.get(
            "/python/curriculum",
            query_string={"return_to": "/python/lessons/missing.md"},
        )
        html = response.get_data(as_text=True)
        header = html.split('<header class="topbar">', 1)[1].split("</header>", 1)[0]

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/learning?topic=python#course-python"', header)
        self.assertNotIn('href="/python/lessons/missing.md"', header)


if __name__ == "__main__":
    unittest.main()
