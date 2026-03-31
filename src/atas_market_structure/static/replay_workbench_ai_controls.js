export function bindWorkbenchAiControls({
  els,
  bindClickAction,
  renderStatusStrip,
  renderSnapshot,
  getActiveThread,
  persistSessions,
  aiChat,
  setSecondaryControlsOpen,
  setSkillPanelVisible,
  syncQuickActionButtonState,
  updateComposerDraft,
  dispatchAiComposerSend,
} = {}) {
  const aiPresetButtons = [
    els?.aiKlineAnalysisButton,
    els?.focusRegionsButton,
    els?.liveDepthButton,
    els?.manualRegionButton,
    els?.selectedBarButton,
  ].filter(Boolean);

  function setAiPresetButtonsBusy(activeButton, busy) {
    aiPresetButtons.forEach((button) => {
      if (!button) {
        return;
      }
      const isTarget = button === activeButton;
      button.disabled = !!busy;
      button.dataset.busy = busy && isTarget ? "true" : "false";
      button.classList.toggle("is-active", !!busy && isTarget);
    });
  }

  async function runAiPresetButtonAction(button, action) {
    if (button?.dataset.busy === "true") {
      return null;
    }
    setAiPresetButtonsBusy(button, true);
    try {
      return await action();
    } catch (error) {
      console.error("AI 快捷动作失败:", error);
      renderStatusStrip?.([{ label: error?.message || String(error), variant: "warn" }]);
      return null;
    } finally {
      setAiPresetButtonsBusy(button, false);
    }
  }

  function initializeSkillPanel() {
    if (!els?.aiSkillPanel || !els?.aiSkillGrid) {
      return;
    }
    const skills = [
      { id: "kline_analysis", name: "K线分析", icon: "📊", prompt: "请分析当前K线图表并给出交易建议" },
      { id: "recent_bars", name: "最近20根K线", icon: "📈", prompt: "请分析最近20根K线并给出交易计划" },
      { id: "focus_regions", name: "重点区域", icon: "🎯", prompt: "请围绕当前重点区域给出计划" },
      { id: "live_depth", name: "实时挂单", icon: "📋", prompt: "请结合当前盘口结构给出建议" },
      { id: "manual_region", name: "手工区域", icon: "✏️", prompt: "请围绕手工区域做标准分析" },
      { id: "selected_bar", name: "选中K线", icon: "🔍", prompt: "请分析当前选中K线" },
    ];
    els.aiSkillGrid.innerHTML = skills.map((skill) => `
      <div class="ai-skill-card" data-skill-id="${skill.id}">
        <div class="ai-skill-icon">${skill.icon}</div>
        <div class="ai-skill-name">${skill.name}</div>
      </div>
    `).join("");
    const skillCards = Array.from(els.aiSkillGrid.querySelectorAll(".ai-skill-card"));
    skillCards.forEach((card) => {
      card.addEventListener("click", async () => {
        const skillId = card.dataset.skillId;
        const skill = skills.find((item) => item.id === skillId);
        if (!skill) {
          return;
        }
        await dispatchAiComposerSend?.({
          button: card,
          extraBusyTargets: skillCards,
          beforeSend: () => {
            updateComposerDraft?.(skill.prompt);
            setSkillPanelVisible?.(false);
            return true;
          },
        });
      });
    });
    if (els.aiSkillSearch) {
      els.aiSkillSearch.addEventListener("input", (event) => {
        const query = String(event.target?.value || "").toLowerCase();
        els.aiSkillGrid.querySelectorAll(".ai-skill-card").forEach((card) => {
          const name = String(card.querySelector(".ai-skill-name")?.textContent || "").toLowerCase();
          card.style.display = name.includes(query) ? "flex" : "none";
        });
      });
    }
  }

  els?.aiChatInput?.addEventListener("input", (event) => {
    const value = String(event.target?.value || "");
    if (value.startsWith("@") || value.startsWith("/")) {
      setSkillPanelVisible?.(true);
    } else if (els.aiSkillPanel && !els.aiSkillPanel.hidden) {
      setSkillPanelVisible?.(false);
    }
  });

  bindClickAction?.(els?.aiKlineAnalysisButton, async () => {
    await runAiPresetButtonAction(els.aiKlineAnalysisButton, async () => {
      const session = getActiveThread?.();
      if (session) {
        session.analysisTemplate = {
          type: "recent_20_bars",
          range: "current_window",
          style: "standard",
          sendMode: "current",
        };
        persistSessions?.();
      }
      if (els.analysisTypeSelect) {
        els.analysisTypeSelect.value = "recent_20_bars";
      }
      if (els.analysisRangeSelect) {
        els.analysisRangeSelect.value = "current_window";
      }
      if (els.analysisStyleSelect) {
        els.analysisStyleSelect.value = "standard";
      }
      await aiChat?.handlePresetAnalysis("recent_20_bars", "请基于当前窗口做标准分析，并聚焦时间、关键价位、对象和风险。", false);
      renderSnapshot?.();
    });
  });

  bindClickAction?.(els?.aiMoreButton, () => {
    setSecondaryControlsOpen?.(!(els.aiSecondaryControls?.open), { announce: true });
  });

  initializeSkillPanel();

  els?.aiSecondaryControls?.addEventListener("toggle", () => {
    if (!els.aiSecondaryControls?.open && els.aiSkillPanel && !els.aiSkillPanel.hidden) {
      els.aiSkillPanel.hidden = true;
    }
    syncQuickActionButtonState?.();
  });

  bindClickAction?.(els?.analysisSendCurrentButton, async () => {
    const session = getActiveThread?.();
    if (session) {
      session.analysisTemplate = {
        type: els.analysisTypeSelect?.value,
        range: els.analysisRangeSelect?.value,
        style: els.analysisStyleSelect?.value,
        sendMode: "current",
      };
      persistSessions?.();
    }
    await aiChat?.handlePresetAnalysis(
      els.analysisTypeSelect?.value,
      `请基于当前${els.analysisRangeSelect?.value}做${els.analysisStyleSelect?.value}风格分析。`,
      false,
    );
    renderSnapshot?.();
  }, {
    useBusyState: true,
    lockKey: "analysis-send-current",
    blockedLabel: "当前分析请求正在发送，请稍候。",
  });

  bindClickAction?.(els?.analysisSendNewButton, async () => {
    await aiChat?.handlePresetAnalysis(
      els.analysisTypeSelect?.value,
      `请基于当前${els.analysisRangeSelect?.value}做${els.analysisStyleSelect?.value}风格分析。`,
      true,
    );
    renderSnapshot?.();
  }, {
    useBusyState: true,
    lockKey: "analysis-send-new",
    blockedLabel: "当前分析请求正在发送，请稍候。",
  });

  bindClickAction?.(els?.focusRegionsButton, async () => {
    await runAiPresetButtonAction(els.focusRegionsButton, async () => {
      await aiChat?.handlePresetAnalysis("focus_regions", "请围绕当前重点区域给出计划。", false);
      renderSnapshot?.();
    });
  });

  bindClickAction?.(els?.liveDepthButton, async () => {
    await runAiPresetButtonAction(els.liveDepthButton, async () => {
      await aiChat?.handlePresetAnalysis("live_depth", "请结合当前盘口结构给出建议。", false);
      renderSnapshot?.();
    });
  });

  bindClickAction?.(els?.manualRegionButton, async () => {
    await runAiPresetButtonAction(els.manualRegionButton, async () => {
      await aiChat?.handlePresetAnalysis("manual_region", aiChat.buildManualRegionAnalysisPrompt(), false);
      renderSnapshot?.();
    });
  });

  bindClickAction?.(els?.selectedBarButton, async () => {
    await runAiPresetButtonAction(els.selectedBarButton, async () => {
      await aiChat?.handlePresetAnalysis("selected_bar", aiChat.buildSelectedBarAnalysisPrompt(), false);
      renderSnapshot?.();
    });
  });
}
