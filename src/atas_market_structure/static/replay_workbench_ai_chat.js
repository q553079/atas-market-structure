export function createAiChatController({
  state,
  els,
  fetchJson,
  renderStatusStrip,
  getActiveThread,
  setActiveThread,
  appendAiChatMessage,
  getPresetThreadMeta,
  createThreadId,
}) {
  async function handleAiChat(preset, userMessage, threadMeta = null) {
    try {
      const trimmedMessage = String(userMessage || "").trim();
      if (!trimmedMessage) {
        throw new Error("请输入要分析的问题。");
      }
      if (!state.currentReplayIngestionId) {
        throw new Error("没有可分析的 replay ingestion。先构建回放。");
      }
      const threadDescriptor = threadMeta || getPresetThreadMeta(preset);
      const thread = setActiveThread(threadDescriptor.id, threadDescriptor.title);
      const history = thread.messages.map((item) => ({
        role: item.role,
        content: item.content,
      }));
      appendAiChatMessage("user", trimmedMessage, { preset }, thread.id, thread.title);
      renderStatusStrip([{ label: "AI 对话生成中", variant: "emphasis" }]);
      const result = await fetchJson("/api/v1/workbench/replay-ai-chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          replay_ingestion_id: state.currentReplayIngestionId,
          preset,
          user_message: trimmedMessage,
          history,
          model_override: els.aiModelOverride.value.trim() || null,
          include_live_context: true,
        }),
      });
      thread.turns.push(result);
      appendAiChatMessage("assistant", result.reply_text, {
        preset: result.preset,
        provider: result.provider,
        model: result.model,
        referenced_strategy_ids: result.referenced_strategy_ids || [],
        live_context_summary: result.live_context_summary || [],
        follow_up_suggestions: result.follow_up_suggestions || [],
      }, thread.id, thread.title);
      renderStatusStrip([
        { label: "AI 对话已完成", variant: "good" },
        { label: result.model, variant: "emphasis" },
      ]);
    } catch (error) {
      renderStatusStrip([{ label: "AI 对话失败", variant: "warn" }]);
      const threadDescriptor = threadMeta || getPresetThreadMeta(preset);
      appendAiChatMessage("assistant", error.message || String(error), { preset, provider: "local-error", model: "-" }, threadDescriptor.id, threadDescriptor.title);
    }
  }

  async function handleAiChatSend() {
    const message = els.aiChatInput.value.trim();
    if (!message) {
      return;
    }
    els.aiChatInput.value = "";
    await handleAiChat("general", message, getActiveThread());
  }

  async function handlePresetAnalysis(preset, message) {
    await handleAiChat(preset, message, getPresetThreadMeta(preset));
  }

  function buildManualRegionAnalysisPrompt() {
    const latestRegion = state.manualRegions[state.manualRegions.length - 1];
    if (!latestRegion) {
      throw new Error("还没有已保存的区域。先在图上框选并保存一个区域。");
    }
    return `请重点分析我标注的区域 "${latestRegion.label}"。我的看法是：${latestRegion.thesis}。请结合当前 replay、历史 footprint、事件和上下文，判断这里是否真的是关键支撑/阻力转换点；如果价格回到此区，需要看到哪些反应才能开仓；哪些情况绝对不能开；止损、第一止盈、扩展止盈应如何规划。`;
  }

  function buildSelectedBarAnalysisPrompt() {
    if (state.selectedCandleIndex === null || !state.snapshot?.candles?.[state.selectedCandleIndex]) {
      throw new Error("还没有选中 K 线。先点击图上的一根 K 线。");
    }
    const candle = state.snapshot.candles[state.selectedCandleIndex];
    const footprint = state.selectedFootprintBar;
    const footprintFacts = footprint?.price_levels?.length
      ? `该 bar 有 ${footprint.price_levels.length} 个 footprint 价位，请结合 bid/ask、delta 和价位成交密度判断其含义。`
      : "当前没有完整 footprint 价位细节。";
    return `请分析我当前选中的 K 线。时间=${new Date(candle.started_at).toLocaleString()}，O=${Number(candle.open).toFixed(2)} H=${Number(candle.high).toFixed(2)} L=${Number(candle.low).toFixed(2)} C=${Number(candle.close).toFixed(2)}，volume=${candle.volume ?? "n/a"} delta=${candle.delta ?? "n/a"}。${footprintFacts} 请判断这根 bar 在当前结构里代表主动发力、吸收、诱导还是衰竭，并说明下一次价格回到相关区域时的可做与不可做方案。`;
  }

  function createNewThread() {
    const thread = setActiveThread(createThreadId(), `新线程 ${state.aiThreads.length + 1}`);
    renderStatusStrip([{ label: `已创建 ${thread.title}`, variant: "emphasis" }]);
    return thread;
  }

  return {
    handleAiChat,
    handleAiChatSend,
    handlePresetAnalysis,
    buildManualRegionAnalysisPrompt,
    buildSelectedBarAnalysisPrompt,
    createNewThread,
  };
}
