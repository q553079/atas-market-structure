export function createAiThreadController({ state, els, escapeHtml }) {
  function ensureThread(threadId, title) {
    let thread = state.aiThreads.find((item) => item.id === threadId);
    if (!thread) {
      thread = {
        id: threadId,
        title,
        messages: [],
        turns: [],
      };
      state.aiThreads.push(thread);
    }
    return thread;
  }

  function getActiveThread() {
    if (!state.activeAiThreadId) {
      state.activeAiThreadId = "main";
    }
    return ensureThread(state.activeAiThreadId, "主线程");
  }

  function setActiveThread(threadId, title = "主线程") {
    const thread = ensureThread(threadId, title);
    state.activeAiThreadId = thread.id;
    renderAiThreadTabs();
    renderAiChat();
    return thread;
  }

  function renderAiThreadTabs() {
    const activeThread = getActiveThread();
    els.aiThreadTabs.innerHTML = "";
    state.aiThreads.forEach((thread) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `thread-tab ${thread.id === activeThread.id ? "active" : ""}`.trim();
      button.textContent = thread.title;
      button.addEventListener("click", () => {
        state.activeAiThreadId = thread.id;
        renderAiThreadTabs();
        renderAiChat();
      });
      els.aiThreadTabs.appendChild(button);
    });
  }

  function appendAiChatMessage(role, content, meta = {}, threadId = null, threadTitle = "主线程") {
    const thread = ensureThread(threadId || state.activeAiThreadId || "main", threadTitle);
    thread.messages.push({ role, content, meta });
    if (!state.activeAiThreadId) {
      state.activeAiThreadId = thread.id;
    }
    renderAiThreadTabs();
    renderAiChat();
  }

  function renderAiChat() {
    renderAiThreadTabs();
    const thread = getActiveThread();
    const messages = thread.messages || [];
    els.aiChatThread.innerHTML = "";
    if (!messages.length) {
      els.aiChatThread.innerHTML = `<div class="empty-note">当前还没有 AI 对话。先构建回放，再点击预设按钮或直接提问。</div>`;
      return;
    }

    messages.forEach((message) => {
      const bubble = document.createElement("div");
      bubble.className = `chat-bubble ${message.role}`;
      const meta = message.meta || {};
      const chips = [];
      if (meta.preset) {
        chips.push(`<span class="chip">${escapeHtml(meta.preset)}</span>`);
      }
      if (meta.provider && meta.model) {
        chips.push(`<span class="chip emphasis">${escapeHtml(`${meta.provider}/${meta.model}`)}</span>`);
      }
      if (meta.referenced_strategy_ids?.length) {
        meta.referenced_strategy_ids.forEach((item) => {
          chips.push(`<span class="chip">${escapeHtml(item)}</span>`);
        });
      }
      bubble.innerHTML = `
        <h4>${escapeHtml(message.role === "user" ? "交易员" : "AI 副驾驶")}</h4>
        <p>${escapeHtml(message.content)}</p>
        ${chips.length ? `<div class="chat-meta">${chips.join("")}</div>` : ""}
        ${meta.live_context_summary?.length ? `<div class="chat-meta">${meta.live_context_summary.map((item) => `<span class="chip">${escapeHtml(item)}</span>`).join("")}</div>` : ""}
        ${meta.follow_up_suggestions?.length ? `<div class="chat-meta">${meta.follow_up_suggestions.map((item) => `<span class="chip warn">${escapeHtml(item)}</span>`).join("")}</div>` : ""}
      `;
      els.aiChatThread.appendChild(bubble);
    });

    els.aiChatThread.scrollTop = els.aiChatThread.scrollHeight;
  }

  return {
    ensureThread,
    getActiveThread,
    setActiveThread,
    renderAiThreadTabs,
    appendAiChatMessage,
    renderAiChat,
  };
}
