(function () {
  function escapeHtml(value) {
    return String(value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  function normalizeParagraphs(text) {
    return String(text || '')
      .split(/\n{2,}/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function formatPrice(value) {
    const num = Number(value);
    return Number.isFinite(num) ? num.toFixed(2) : '待定';
  }

  function renderPlanMetrics(planCard) {
    const metrics = [
      `方向 ${escapeHtml(planCard.side === 'sell' ? '空' : planCard.side === 'buy' ? '多' : '中性')}`,
      `入场 ${escapeHtml(formatPrice(planCard.entryPrice ?? planCard.entryPriceLow))}`,
      `止损 ${escapeHtml(formatPrice(planCard.stopPrice))}`,
      `TP1 ${escapeHtml(formatPrice(planCard.targetPrice))}`,
    ];
    if (planCard.targetPrice2 != null) {
      metrics.push(`TP2 ${escapeHtml(formatPrice(planCard.targetPrice2))}`);
    }
    if (planCard.confidenceLabel) {
      metrics.push(`置信 ${escapeHtml(planCard.confidenceLabel)}`);
    }
    return metrics.map((item) => `<span class="plan-chip">${item}</span>`).join('');
  }

  function renderPlanCardHtml(planCard) {
    if (!planCard || typeof planCard !== 'object') {
      return '';
    }
    return `
      <div class="chat-plan-card" data-plan-id="${escapeHtml(planCard.id || '')}" data-session-id="${escapeHtml(planCard.sessionId || '')}" data-message-id="${escapeHtml(planCard.messageId || '')}">
        <div class="chat-plan-card-head">
          <strong>${escapeHtml(planCard.title || 'AI计划')}</strong>
          <span class="plan-chip status">${escapeHtml(planCard.status || 'active')}</span>
        </div>
        <div class="chat-plan-card-summary">${escapeHtml(planCard.summary || planCard.notes || '结构化交易计划')}</div>
        <div class="chat-plan-card-metrics">${renderPlanMetrics(planCard)}</div>
        <div class="chat-plan-card-actions">
          <button type="button" class="plan-action" data-plan-action="show">上图</button>
          <button type="button" class="plan-action" data-plan-action="focus">只看此计划</button>
          <button type="button" class="plan-action" data-plan-action="jump">查看图表</button>
        </div>
      </div>
    `;
  }

  function collectMessagePlanCards(message) {
    const cards = [];
    if (Array.isArray(message?.planCards)) {
      cards.push(...message.planCards.filter(Boolean));
    }
    if (message?.planCard && typeof message.planCard === 'object') {
      cards.push(message.planCard);
    }
    if (Array.isArray(message?.meta?.planCards)) {
      cards.push(...message.meta.planCards.filter(Boolean));
    }
    if (message?.meta?.planCard && typeof message.meta.planCard === 'object') {
      cards.push(message.meta.planCard);
    }
    const seen = new Set();
    return cards.filter((item) => {
      const key = item?.id || item?.plan_id || JSON.stringify(item);
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function buildRichTextHtml(content) {
    const paragraphs = normalizeParagraphs(content || '');
    if (!paragraphs.length) {
      return '<p></p>';
    }
    return paragraphs.map((item) => `<p>${escapeHtml(item)}</p>`).join('');
  }

  function extractAttachmentSummaries(message) {
    const items = Array.isArray(message?.meta?.attachment_summaries)
      ? message.meta.attachment_summaries
      : [];
    if (!items.length) {
      return '';
    }
    return `
      <div class="chat-attachment-summary-row">
        ${items.map((item) => `<span class="attachment-summary-chip">${escapeHtml(String(item))}</span>`).join('')}
      </div>
    `;
  }

  function tryParseJsonText(text) {
    const raw = String(text || '').trim();
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch (error) {
      return null;
    }
  }

  function deriveMessageContent(message) {
    if (message == null) {
      return '';
    }
    if (typeof message === 'string') {
      return message;
    }
    if (typeof message.content === 'string' && message.content.trim()) {
      return message.content;
    }
    if (typeof message.reply_text === 'string' && message.reply_text.trim()) {
      return message.reply_text;
    }
    if (typeof message.request_message === 'string' && message.request_message.trim()) {
      return message.request_message;
    }
    if (typeof message.raw_text === 'string' && message.raw_text.trim()) {
      const parsed = tryParseJsonText(message.raw_text);
      if (parsed && typeof parsed.reply_text === 'string' && parsed.reply_text.trim()) {
        return parsed.reply_text;
      }
      return message.raw_text;
    }
    return '';
  }

  function normalizeMessage(message) {
    const normalized = (message && typeof message === 'object') ? { ...message } : { content: message };
    const role = normalized.role === 'user' ? 'user' : 'assistant';
    const meta = (normalized.meta && typeof normalized.meta === 'object') ? { ...normalized.meta } : {};

    if (!meta.preset && normalized.preset) meta.preset = normalized.preset;
    if (!meta.provider && normalized.provider) meta.provider = normalized.provider;
    if (!meta.model && normalized.model) meta.model = normalized.model;
    if (!Array.isArray(meta.referenced_strategy_ids) && Array.isArray(normalized.referenced_strategy_ids)) {
      meta.referenced_strategy_ids = normalized.referenced_strategy_ids;
    }
    if (!Array.isArray(meta.live_context_summary) && Array.isArray(normalized.live_context_summary)) {
      meta.live_context_summary = normalized.live_context_summary;
    }
    if (!Array.isArray(meta.follow_up_suggestions) && Array.isArray(normalized.follow_up_suggestions)) {
      meta.follow_up_suggestions = normalized.follow_up_suggestions;
    }
    if (!Array.isArray(meta.attachment_summaries) && Array.isArray(normalized.attachment_summaries)) {
      meta.attachment_summaries = normalized.attachment_summaries;
    }

    normalized.role = role;
    normalized.meta = meta;
    normalized.content = deriveMessageContent(normalized);
    return normalized;
  }

  function buildBubbleHtml(message) {
    const normalizedMessage = normalizeMessage(message);
    const content = normalizedMessage.content || '';
    const planCards = collectMessagePlanCards(normalizedMessage);
    const attachmentsHtml = extractAttachmentSummaries(normalizedMessage);
    return `
      <div class="chat-bubble-body">${buildRichTextHtml(content)}</div>
      ${attachmentsHtml}
      ${planCards.length ? `<div class="chat-plan-card-list">${planCards.map((plan) => renderPlanCardHtml(plan)).join('')}</div>` : ''}
    `;
  }

  function createMessageNode(message) {
    const normalizedMessage = normalizeMessage(message);
    const role = normalizedMessage.role === 'user' ? 'user' : 'assistant';
    const wrapper = document.createElement('div');
    wrapper.className = `chat-message ${role}`;
    if (normalizedMessage.message_id) {
      wrapper.dataset.messageId = normalizedMessage.message_id;
    }
    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${role}`;
    bubble.innerHTML = buildBubbleHtml(normalizedMessage);
    wrapper.appendChild(bubble);
    return wrapper;
  }

  function renderThread(container, messages, emptyHtml) {
    if (!container) return;
    container.innerHTML = '';
    if (!Array.isArray(messages) || !messages.length) {
      const empty = document.createElement('div');
      empty.className = 'chat-empty-state';
      empty.innerHTML = emptyHtml || '暂无消息';
      container.appendChild(empty);
      return;
    }
    messages
      .map((message) => normalizeMessage(message))
      .forEach((message) => container.appendChild(createMessageNode(message)));
    container.scrollTop = container.scrollHeight;
  }

  function mountModule(root) {
    if (!root || root.dataset.chatModuleReady === 'true') return;
    root.classList.add('ai-chat-module');
    root.dataset.chatModuleReady = 'true';
  }

  window.ReplayChatWindow = {
    mountModule,
    renderThread,
    buildBubbleHtml,
    normalizeMessage,
  };
})();
