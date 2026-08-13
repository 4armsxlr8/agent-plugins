(() => {
  // ---------- Sidebar toggle ----------
  // 初期反映は <head> 内の inline script で完了済み（flash 防止のため）。
  // ここではボタンクリックと aria-expanded の同期のみ。
  const SB_KEY = "study-loop-sidebar";
  const htmlEl = document.documentElement;
  const sbToggle = document.getElementById("sidebar-toggle");
  if (sbToggle) {
    const mobileSidebar = window.matchMedia("(max-width: 960px)");
    const reflect = () => {
      const state = htmlEl.getAttribute("data-sidebar");
      const collapsed = state === "closed" || (mobileSidebar.matches && state !== "open");
      sbToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
      sbToggle.setAttribute("aria-label", collapsed ? "レッスン一覧を開く" : "レッスン一覧を閉じる");
    };
    const closeSidebar = () => {
      htmlEl.setAttribute("data-sidebar", "closed");
      localStorage.setItem(SB_KEY, "closed");
      reflect();
      sbToggle.focus();
    };
    reflect();
    sbToggle.addEventListener("click", () => {
      const state = htmlEl.getAttribute("data-sidebar");
      const collapsed = state === "closed" || (mobileSidebar.matches && state !== "open");
      const next = collapsed ? "open" : "closed";
      htmlEl.setAttribute("data-sidebar", next);
      localStorage.setItem(SB_KEY, next);
      reflect();
    });
    document.querySelectorAll("[data-sidebar-close]").forEach((close) => {
      close.addEventListener("click", closeSidebar);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || htmlEl.getAttribute("data-sidebar") !== "open") return;
      event.preventDefault();
      closeSidebar();
    });
    mobileSidebar.addEventListener?.("change", reflect);
  }

  // ---------- Theme toggle ----------
  const root = document.documentElement;
  const stored = localStorage.getItem("study-loop-theme");
  if (stored) root.setAttribute("data-theme", stored);
  const btn = document.getElementById("theme-toggle");
  if (btn) {
    btn.addEventListener("click", () => {
      const cur = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", cur);
      localStorage.setItem("study-loop-theme", cur);
      // Mermaid のテーマも切り替え（再描画）
      reRenderMermaid();
    });
  }

  // ---------- New learning: full-screen chat interview ----------
  const setupRoot = document.querySelector("[data-setup-chat]");
  if (setupRoot) {
    const form = setupRoot.querySelector("#setup-chat-form");
    const thread = setupRoot.querySelector("#setup-thread");
    const answerInput = setupRoot.querySelector("#setup-answer");
    const quickRoot = setupRoot.querySelector("#setup-quick-replies");
    const dock = setupRoot.querySelector(".setup-dock");
    const error = setupRoot.querySelector("#setup-error");
    const progress = document.querySelector("#setup-progress");
    const questions = [
      { question: "何を学びたいですか？", placeholder: "例: Next.js のデータ取得" },
      { question: "学んだあと、何ができるようになれば成功ですか？", placeholder: "例: 自分で設計して実装できる" },
      { question: "期限・使える環境・今回は扱わない範囲があれば教えてください。なければ「なし」で構いません。", placeholder: "例: 8月末まで。認証は対象外" },
      { question: "どのくらいの期間、使える状態を保ちたいですか？", placeholder: "期間を入力、または候補から選択", replies: ["1週間", "1か月", "3か月", "半年以上"] },
      { question: "学習に使える時間を教えてください。", placeholder: "時間を入力、または候補から選択", replies: ["1日15分", "1日30分", "週3回"] },
    ];
    const answers = [];

    const message = (role, text) => {
      const wrap = document.createElement("div");
      wrap.className = `setup-message ${role}`;
      if (role === "assistant") {
        const avatar = document.createElement("span");
        avatar.className = "setup-avatar";
        avatar.setAttribute("aria-hidden", "true");
        avatar.innerHTML = '<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 5C11.5 5 5 11.5 5 19c7.5 0 14-6.5 14-14Z"/><path d="M17.5 6.5 8 16"/></svg>';
        wrap.append(avatar);
      }
      const body = document.createElement("div");
      const speaker = document.createElement("span");
      speaker.className = "setup-speaker";
      speaker.textContent = role === "assistant" ? "Study Loop" : "あなた";
      const copy = document.createElement("p");
      copy.textContent = text;
      body.append(speaker, copy);
      wrap.append(body);
      return wrap;
    };

    const scrollThread = () => {
      requestAnimationFrame(() => {
        window.scrollTo({
          top: document.documentElement.scrollHeight,
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        });
      });
    };

    const updateComposer = () => {
      const current = questions[answers.length];
      if (progress) {
        progress.textContent = answers.length === questions.length
          ? "質問 5 / 5 · 完了"
          : `質問 ${answers.length + 1} / 5`;
      }
      quickRoot.replaceChildren();
      if (!current) return;
      answerInput.placeholder = current.placeholder;
      (current.replies || []).forEach((reply) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "quick-reply";
        button.textContent = reply;
        button.addEventListener("click", () => submitAnswer(reply));
        quickRoot.append(button);
      });
      answerInput.value = "";
      answerInput.focus({ preventScroll: true });
    };

    const fillSetupFields = () => {
      const values = {
        topic: answers[0],
        why: `「${answers[0]}」を学び、${answers[1]}`,
        success_criteria: `${answers[1]}\n学んだ内容を実際の課題に適用し、判断理由を説明できる`,
        constraints: answers[2],
        out_of_scope: `ヒアリング内容: ${answers[2]}`,
        retention_interval: answers[3],
        time_budget: answers[4],
      };
      Object.entries(values).forEach(([name, value]) => {
        form.elements.namedItem(name).value = value;
      });
    };

    const renderSummary = () => {
      fillSetupFields();
      if (progress) progress.textContent = "質問 5 / 5 · 完了";
      thread.append(message("assistant", "必要な情報がそろいました。内容を確認してください。"));
      const card = document.createElement("section");
      card.className = "setup-summary-card";
      const title = document.createElement("h2");
      title.textContent = "学習目標の確認";
      title.tabIndex = -1;
      const list = document.createElement("dl");
      const labels = ["トピック", "成功条件", "制約・対象外", "保持期間", "時間予算"];
      answers.forEach((value, index) => {
        const row = document.createElement("div");
        row.className = "setup-summary-row";
        const term = document.createElement("dt");
        term.textContent = labels[index];
        const description = document.createElement("dd");
        description.textContent = value;
        row.append(term, description);
        list.append(row);
      });
      const target = document.createElement("div");
      target.className = "setup-summary-row";
      const targetLabel = document.createElement("dt");
      targetLabel.textContent = "推奨目標";
      const targetValue = document.createElement("dd");
      targetValue.textContent = "Level 4 — 自分で判断し、実際の課題に適用できる";
      target.append(targetLabel, targetValue);
      list.append(target);
      const actions = document.createElement("div");
      actions.className = "setup-summary-actions";
      const submit = document.createElement("button");
      submit.type = "submit";
      submit.className = "btn btn-primary";
      submit.textContent = "この内容で診断を始める";
      const restart = document.createElement("button");
      restart.type = "button";
      restart.className = "setup-restart";
      restart.textContent = "最初からやり直す";
      restart.addEventListener("click", () => {
        answers.length = 0;
        thread.replaceChildren(message("assistant", questions[0].question));
        dock.hidden = false;
        updateComposer();
        scrollThread();
      });
      actions.append(submit, restart);
      card.append(title, list, actions);
      thread.append(card);
      dock.hidden = true;
      title.focus({ preventScroll: true });
      scrollThread();
    };

    function submitAnswer(value) {
      const answer = String(value || "").trim();
      if (!answer) {
        error.hidden = false;
        answerInput.focus();
        return;
      }
      error.hidden = true;
      thread.append(message("user", answer));
      answers.push(answer);
      if (answers.length === questions.length) {
        renderSummary();
      } else {
        thread.append(message("assistant", questions[answers.length].question));
        updateComposer();
        scrollThread();
      }
    }

    form.addEventListener("submit", (event) => {
      if (answers.length < questions.length) {
        event.preventDefault();
        submitAnswer(answerInput.value);
      }
    });
    answerInput.addEventListener("input", () => {
      if (answerInput.value.trim()) error.hidden = true;
    });
    updateComposer();
  }

  // ---------- Mermaid ----------
  function reRenderMermaid() {
    if (!window.mermaid) return;
    const isDark = root.getAttribute("data-theme") === "dark";
    window.mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: isDark ? "dark" : "default",
      themeVariables: {
        fontFamily: '"Hanken Grotesk", "Noto Sans JP", sans-serif',
      },
    });
    // 既存の svg を消して再描画
    document.querySelectorAll(".mermaid-rendered").forEach((el) => {
      el.classList.remove("mermaid-rendered");
      el.textContent = el.dataset.source || el.textContent;
    });
    transformAndRenderMermaid();
  }

  function transformAndRenderMermaid() {
    // ```mermaid のフェンスドコードを <pre class="mermaid"> に変換
    document
      .querySelectorAll('pre code.language-mermaid, pre > code.mermaid')
      .forEach((code) => {
        const pre = code.parentElement;
        const div = document.createElement("div");
        div.className = "mermaid";
        div.dataset.source = code.textContent;
        div.textContent = code.textContent;
        pre.replaceWith(div);
      });
    if (window.mermaid) {
      try {
        window.mermaid.run({ querySelector: ".mermaid:not(.mermaid-rendered)" });
        document.querySelectorAll(".mermaid").forEach((el) => {
          el.classList.add("mermaid-rendered");
        });
      } catch (e) {
        console.warn("Mermaid render error", e);
      }
    }
  }

  // mermaid モジュールはロードに時間がかかる。100ms ポーリング
  const waitMermaid = setInterval(() => {
    if (window.mermaid) {
      clearInterval(waitMermaid);
      reRenderMermaid();
    }
  }, 100);

  // ---------- Textarea: autosize + Cmd/Ctrl + Enter で submit ----------
  document.querySelectorAll("textarea").forEach((ta) => {
    const grow = () => {
      ta.style.height = "auto";
      const minimum = Number(ta.dataset.minHeight || 200);
      ta.style.height = Math.max(ta.scrollHeight + 4, minimum) + "px";
    };
    ta.addEventListener("input", grow);
    grow();

    ta.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        const form = ta.closest("form");
        if (form) form.requestSubmit();
      }
    });
  });

  document.querySelectorAll(".code-input").forEach((textarea) => {
    textarea.addEventListener("keydown", (event) => {
      if (event.key !== "]" || (!event.metaKey && !event.ctrlKey)) return;
      event.preventDefault();
      const start = textarea.selectionStart;
      textarea.setRangeText("  ", start, textarea.selectionEnd, "end");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
  });

  // ---------- Lesson tasks: local completion before the existing Markdown submit ----------
  const lessonTaskForm = document.querySelector(".lesson-task-form");
  if (lessonTaskForm) {
    const tasks = [...lessonTaskForm.querySelectorAll("[data-task-id]")];
    const total = Number(lessonTaskForm.dataset.taskTotal || tasks.length);
    const completed = new Set();
    const submit = lessonTaskForm.querySelector(".lvd-submit");
    const count = lessonTaskForm.querySelector("#completed-task-count");
    const note = lessonTaskForm.querySelector("#lesson-submit-note");
    const progressBar = lessonTaskForm.querySelector(".task-progress");
    const draftKey = `study-loop-lesson-draft:${window.location.pathname}`;
    const draftFields = [...lessonTaskForm.querySelectorAll(".lvd-textarea, .lvd-memo")];
    const allGraded = tasks.length > 0 && tasks.every((task) => task.dataset.graded === "true");
    const saveDraft = () => {
      if (allGraded) return;
      try {
        const values = Object.fromEntries(
          draftFields.filter((field) => field.id).map((field) => [field.id, field.value]),
        );
        localStorage.setItem(draftKey, JSON.stringify(values));
      } catch {
        // The final submit still writes the answer even when browser storage is unavailable.
      }
    };
    if (allGraded) {
      localStorage.removeItem(draftKey);
    } else {
      try {
        const values = JSON.parse(localStorage.getItem(draftKey) || "{}");
        draftFields.forEach((field) => {
          if (!field.id || typeof values[field.id] !== "string") return;
          field.value = values[field.id];
          field.dispatchEvent(new Event("input", { bubbles: true }));
        });
      } catch {
        localStorage.removeItem(draftKey);
      }
    }
    if (progressBar && total) progressBar.style.gridTemplateColumns = `repeat(${total}, minmax(0, 1fr))`;

    const taskFields = (task) => [...task.querySelectorAll(".lvd-textarea:not([data-optional])")];
    const taskIsComplete = (task) => {
      const fields = taskFields(task);
      const legacy = task.querySelector(".lvd-textarea[data-optional]");
      return Boolean(legacy?.value.trim()) || (fields.length > 0 && fields.every((field) => field.value.trim()));
    };
    tasks.forEach((task) => {
      const id = Number(task.dataset.taskId);
      if (task.dataset.graded === "true" || taskIsComplete(task)) completed.add(id);
    });

    const setOpenTask = (targetId) => {
      tasks.forEach((task) => {
        const open = Number(task.dataset.taskId) === targetId;
        task.classList.toggle("is-open", open);
        const content = task.querySelector(".task-content");
        const toggle = task.querySelector("[data-task-toggle]");
        if (content) content.hidden = !open;
        if (toggle) toggle.setAttribute("aria-expanded", String(open));
      });
    };

    const syncTasks = () => {
      if (count) count.textContent = String(completed.size);
      lessonTaskForm.querySelectorAll("[data-task-progress]").forEach((item) => {
        item.classList.toggle("done", completed.has(Number(item.dataset.taskProgress)));
      });
      tasks.forEach((task) => {
        if (task.dataset.graded === "true") return;
        const id = Number(task.dataset.taskId);
        const status = task.querySelector(".task-status");
        if (!status) return;
        const saved = completed.has(id);
        status.textContent = saved ? "回答済み" : task.classList.contains("is-open") ? "現在" : "未回答";
        status.className = `task-status${saved ? " saved" : ""}`;
      });
      if (submit) submit.disabled = completed.size < total;
      if (note) {
        const remaining = Math.max(total - completed.size, 0);
        note.textContent = remaining
          ? `残り${remaining}問に回答すると採点できます。`
          : "回答がそろいました。採点へ進めます。";
      }
    };

    tasks.forEach((task) => {
      const id = Number(task.dataset.taskId);
      task.querySelector("[data-task-toggle]")?.addEventListener("click", () => {
        setOpenTask(task.classList.contains("is-open") ? 0 : id);
        syncTasks();
      });
      task.querySelector("[data-save-task]")?.addEventListener("click", () => {
        const fields = taskFields(task);
        const legacy = task.querySelector(".lvd-textarea[data-optional]");
        const legacyComplete = Boolean(legacy?.value.trim());
        let firstInvalid = null;
        fields.forEach((field) => {
          const invalid = !legacyComplete && !field.value.trim();
          const fieldError = field.parentElement?.querySelector(".field-error");
          if (fieldError) fieldError.hidden = !invalid;
          field.setAttribute("aria-invalid", String(invalid));
          if (invalid && !firstInvalid) firstInvalid = field;
        });
        if (firstInvalid) {
          firstInvalid.focus();
          return;
        }
        completed.add(id);
        saveDraft();
        const next = tasks.find((candidate) => {
          const candidateId = Number(candidate.dataset.taskId);
          return candidateId > id && !completed.has(candidateId);
        }) || tasks.find((candidate) => !completed.has(Number(candidate.dataset.taskId)));
        setOpenTask(next ? Number(next.dataset.taskId) : 0);
        syncTasks();
        requestAnimationFrame(() => {
          (next || lessonTaskForm.querySelector(".lesson-submit"))?.scrollIntoView({
            behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
            block: "nearest",
          });
          const focusTarget = next?.querySelector(".lvd-textarea")
            || next?.querySelector("[data-task-toggle]")
            || lessonTaskForm.querySelector(".lvd-submit");
          focusTarget?.focus({ preventScroll: true });
        });
      });
      task.querySelectorAll(".lvd-textarea").forEach((field) => {
        field.addEventListener("input", () => {
          saveDraft();
          const fieldError = field.parentElement?.querySelector(".field-error");
          if (field.value.trim()) {
            field.removeAttribute("aria-invalid");
            if (fieldError) fieldError.hidden = true;
          }
          if (completed.delete(id)) syncTasks();
        });
      });
    });
    lessonTaskForm.querySelector(".lvd-memo")?.addEventListener("input", saveDraft);

    lessonTaskForm.addEventListener("submit", (event) => {
      if (completed.size >= total) return;
      event.preventDefault();
      const firstIncomplete = tasks.find((task) => !completed.has(Number(task.dataset.taskId)));
      if (!firstIncomplete) return;
      setOpenTask(Number(firstIncomplete.dataset.taskId));
      firstIncomplete.querySelector("[data-save-task]")?.click();
    });
    syncTasks();
  }

  // ---------- Prism: 言語不明の code block にもスタイルを与える ----------
  document.querySelectorAll('pre code:not([class])').forEach((c) => {
    c.classList.add("language-plaintext");
  });
  if (window.Prism) window.Prism.highlightAll();

  // ---------- Local Codex job controls ----------
  // All task text, paths and working directories are constructed by the
  // server. The browser can select one named action and submit only the
  // small, action-specific fields shown in the UI.
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const jobError = (root, text) => {
    const target = root?.querySelector?.('[data-job-error]') || document.querySelector('[data-job-error]');
    if (target) target.textContent = text || "";
  };
  const startJob = async (action, data, topic, root = document) => {
    const query = topic && action !== "session_start" ? `?topic=${encodeURIComponent(topic)}` : "";
    const response = await fetch(`/api/jobs${query}`, {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
      credentials: "same-origin",
      body: JSON.stringify({action, data}),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      jobError(root, body.message || "Codex を開始できませんでした。手動で続けられます。");
      return;
    }
    window.location.assign(`/jobs/${encodeURIComponent(body.id)}`);
  };

  document.querySelectorAll('[data-codex-status]').forEach(async (el) => {
    try {
      const response = await fetch('/api/codex/status', {credentials: 'same-origin'});
      const status = await response.json();
      el.textContent = status.installed && status.backend !== 'manual' ? 'Codex を利用可能' : '手動モードを利用可能';
      el.title = status.message;
    } catch (_) {
      el.textContent = '手動モードを利用可能';
    }
  });

  document.querySelectorAll('[data-start-action]').forEach((button) => {
    button.addEventListener('click', () => {
      const action = button.dataset.startAction;
      const topic = button.dataset.topic;
      const explanation = button.closest('.page')?.querySelector('[data-self-explanation]')?.value?.trim();
      const confirmationToken = button.dataset.confirmationToken;
      const data = confirmationToken ? {confirmationToken} : {};
      if (explanation && ['lesson_grade', 'diagnostic_grade'].includes(action)) data.selfExplanation = explanation;
      startJob(action, data, topic, button.closest('.codex-controls, .page'));
    });
  });

  document.querySelectorAll('[data-create-codex-session]').forEach((button) => {
    button.addEventListener('click', () => {
      try {
        startJob('session_start', JSON.parse(button.dataset.payload || '{}'), '', button.closest('.page'));
      } catch (_) {
        jobError(button.closest('.page'), '開始内容を読み取れませんでした。編集してもう一度試してください。');
      }
    });
  });

  document.querySelectorAll('[data-revise-curriculum]').forEach((button) => {
    button.addEventListener('click', () => {
      const feedback = button.closest('.codex-controls')?.querySelector('[data-curriculum-feedback]')?.value?.trim();
      if (!feedback) return jobError(button.closest('.codex-controls'), '修正したいことを入力してください。');
      startJob('curriculum_revise', {feedback}, button.dataset.topic, button.closest('.codex-controls'));
    });
  });

  const jobRoot = document.querySelector('[data-job-id]');
  if (jobRoot) {
    const jobId = jobRoot.dataset.jobId;
    const statusEl = jobRoot.querySelector('[data-job-status]');
    const phaseEl = jobRoot.querySelector('[data-job-phase]');
    const messageEl = jobRoot.querySelector('[data-job-message]');
    const inputForm = jobRoot.querySelector('[data-job-input]');
    const questionsRoot = jobRoot.querySelector('[data-job-questions]');
    const approval = jobRoot.querySelector('[data-job-approval]');
    const cancel = jobRoot.querySelector('[data-cancel-job]');
    const result = jobRoot.querySelector('[data-job-result]');
    const diagnosticDecision = jobRoot.querySelector('[data-diagnostic-decision]');
    const lessonDecision = jobRoot.querySelector('[data-lesson-decision]');
    const renderQuestions = (questions) => {
      questionsRoot.replaceChildren();
      (questions || []).forEach((question) => {
        const wrap = document.createElement('fieldset');
        const legend = document.createElement('legend'); legend.textContent = question.header || '質問'; wrap.append(legend);
        const prompt = document.createElement('p'); prompt.textContent = question.question || ''; wrap.append(prompt);
        let field;
        if (Array.isArray(question.options) && question.options.length) {
          field = document.createElement('select');
          question.options.forEach((option) => { const item = document.createElement('option'); item.value = option.label; item.textContent = `${option.label} — ${option.description}`; field.append(item); });
          if (question.isOther) { const other = document.createElement('option'); other.value = '__other__'; other.textContent = 'その他（下に入力）'; field.append(other); }
        } else {
          field = document.createElement(question.isSecret ? 'input' : 'textarea');
          if (question.isSecret) field.type = 'password'; else field.rows = 3;
          field.maxLength = 4000;
        }
        field.dataset.questionId = question.id; field.required = true; wrap.append(field);
        if (question.isOther) {
          const otherText = document.createElement('input'); otherText.type = question.isSecret ? 'password' : 'text'; otherText.maxLength = 4000; otherText.placeholder = 'その他の回答'; otherText.dataset.otherFor = question.id; otherText.hidden = true; wrap.append(otherText);
          const syncOther = () => { const choosingOther = field.value === '__other__'; field.required = !choosingOther; otherText.required = choosingOther; otherText.hidden = !choosingOther; };
          field.addEventListener('change', syncOther); syncOther();
        }
        questionsRoot.append(wrap);
      });
    };
    const apply = (job) => {
      statusEl.textContent = job.status;
      phaseEl.textContent = job.phase;
      messageEl.textContent = job.message;
      jobError(jobRoot, job.error);
      inputForm.hidden = job.status !== 'waiting_input';
      approval.hidden = job.status !== 'waiting_approval';
      if (job.status === 'waiting_input') renderQuestions(job.details?.questions);
      if (job.status === 'waiting_approval') {
        const details = job.details || {};
        [['reason', details.reason], ['command', details.command], ['cwd', details.cwd], ['network', details.networkHost], ['paths', (details.paths || []).join(', ')], ['permissions', details.permissions]].forEach(([key, value]) => {
          const target = approval.querySelector(`[data-detail-${key}]`); if (target) target.textContent = value || 'なし';
        });
        approval.querySelectorAll('[data-approval]').forEach((button) => {
          button.hidden = !Array.isArray(details.decisions) || !details.decisions.includes(button.dataset.approval);
        });
      }
      cancel.hidden = ['completed', 'failed', 'cancelled'].includes(job.status);
      if (job.status === 'completed' && job.result) {
        result.hidden = false;
        result.querySelector('[data-job-summary]').textContent = job.result.summary;
        const link = result.querySelector('[data-job-result-link]');
        link.hidden = !job.nextUrl;
        if (job.nextUrl) link.href = job.nextUrl;
        diagnosticDecision.hidden = !(job.action === 'diagnostic_grade' && job.canAcceptDiagnostic === true);
        lessonDecision.hidden = !(job.action === 'lesson_grade' && job.lessonResolution);
        lessonDecision.dataset.sourceJobId = job.lessonResolution?.sourceJobId || '';
      }
    };
    const send = async (suffix, body = {}) => {
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}${suffix}`, {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
        credentials: 'same-origin', body: JSON.stringify(body),
      });
      const job = await response.json().catch(() => ({}));
      if (!response.ok) return jobError(jobRoot, job.message || '操作を完了できませんでした。');
      apply(job);
    };
    inputForm.addEventListener('submit', (event) => {
      event.preventDefault();
      const answers = {};
      questionsRoot.querySelectorAll('[data-question-id]').forEach((field) => {
        const other = questionsRoot.querySelector(`[data-other-for="${CSS.escape(field.dataset.questionId)}"]`);
        const useOther = field.value === '__other__';
        const value = field.value === '__other__' ? other?.value : field.value;
        if (!useOther && other) other.value = '';
        answers[field.dataset.questionId] = [value];
      });
      send('/responses', {answers});
    });
    approval.querySelectorAll('[data-approval]').forEach((button) => {
      button.addEventListener('click', () => {
        const decision = button.dataset.approval;
        if (decision === 'cancel') send('/responses', {decision}); else send('/responses', {decision});
      });
    });
    cancel.addEventListener('click', () => send('/cancel'));
    jobRoot.querySelector('[data-accept-diagnostic]').addEventListener('click', () => {
      const adjustment = jobRoot.querySelector('[data-diagnostic-adjustment]').value.trim();
      startJob('diagnostic_accept', adjustment ? {adjustment} : {}, jobRoot.dataset.topic, jobRoot);
    });
    lessonDecision.querySelectorAll('[data-lesson-resolution]').forEach((button) => {
      button.addEventListener('click', () => {
        const sourceJobId = lessonDecision.dataset.sourceJobId;
        if (!sourceJobId) return;
        startJob('lesson_grade', {followupJobId: sourceJobId, resolution: button.dataset.lessonResolution}, jobRoot.dataset.topic, jobRoot);
      });
    });
    const events = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/events`);
    ['status', 'commentary'].forEach((name) => events.addEventListener(name, (event) => {
      try { const job = JSON.parse(event.data); apply(job); if (['completed', 'failed', 'cancelled'].includes(job.status)) events.close(); } catch (_) {}
    }));
  }

  // ---------- Scroll-entry reveal（IntersectionObserver） ----------
  // .reveal は html.js のとき隠れている。表示域に入ったら .in を付けて出す。
  const reveals = document.querySelectorAll(".reveal");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reveals.length && "IntersectionObserver" in window && !reduceMotion) {
    const io = new IntersectionObserver(
      (entries, obs) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("in");
            obs.unobserve(e.target);
          }
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.05 }
    );
    reveals.forEach((el) => io.observe(el));
  } else {
    // IO 非対応 or reduced-motion: 即時表示
    reveals.forEach((el) => el.classList.add("in"));
  }
})();
