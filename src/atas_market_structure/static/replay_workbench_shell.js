export function createWorkbenchShell({
  state,
  els,
  renderChart,
  getHandleBuild,
}) {
  function scheduleChartRerender() {
    if (state.pendingChartRerender) {
      return;
    }
    state.pendingChartRerender = true;
    window.requestAnimationFrame(() => {
      state.pendingChartRerender = false;
      if (state.snapshot?.candles?.length) {
        if (window._lwChartState) {
          const { resizeCharts } = window._lwChartState;
          if (resizeCharts) {
            resizeCharts(els);
          }
        }
        renderChart();
      }
    });
  }

  function setBuildProgress(active, percent = 0, label = "") {
    els.buildProgress.classList.toggle("active", active);
    els.buildProgressFill.style.width = `${Math.max(0, Math.min(100, percent))}%`;
    els.buildProgressPercent.textContent = `${Math.round(Math.max(0, Math.min(100, percent)))}%`;
    if (label) {
      els.buildProgressLabel.textContent = label;
    }
  }

  function initializeSectionToggles() {
    document.querySelectorAll(".sidebar .section").forEach((section, index) => {
      if (section.dataset.toggleReady === "true") {
        return;
      }
      const heading = section.querySelector(":scope > h3");
      if (!heading) {
        return;
      }
      const content = document.createElement("div");
      content.className = "section-content";
      while (heading.nextSibling) {
        content.appendChild(heading.nextSibling);
      }
      const header = document.createElement("div");
      header.className = "section-header";
      const title = document.createElement("h3");
      title.textContent = heading.textContent;
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "section-toggle";
      toggle.textContent = "收起";
      toggle.addEventListener("click", () => {
        const collapsed = section.classList.toggle("collapsed");
        toggle.textContent = collapsed ? "展开" : "收起";
      });
      header.appendChild(title);
      header.appendChild(toggle);
      section.innerHTML = "";
      section.appendChild(header);
      section.appendChild(content);
      section.dataset.toggleReady = "true";
      if (index >= 4) {
        section.classList.add("collapsed");
        toggle.textContent = "展开";
      }
    });
  }

  async function handleBuildWithForceRefresh() {
    const previous = els.forceRebuild.checked;
    els.forceRebuild.checked = true;
    try {
      await getHandleBuild()();
    } finally {
      els.forceRebuild.checked = previous;
    }
  }

  return {
    scheduleChartRerender,
    setBuildProgress,
    initializeSectionToggles,
    handleBuildWithForceRefresh,
  };
}
