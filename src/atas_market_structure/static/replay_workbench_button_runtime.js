export function createButtonRuntime({ renderStatusStrip }) {
  const uiActionLocks = new Set();
  const buttonFeedbackTimers = new WeakMap();
  let buttonFeedbackInstalled = false;

  function setButtonBusy(button, busy) {
    if (!button) {
      return;
    }
    button.dataset.busy = busy ? "true" : "false";
    button.setAttribute("aria-busy", busy ? "true" : "false");
    if ("disabled" in button) {
      if (busy) {
        button.dataset.wasDisabled = button.disabled ? "true" : "false";
        button.disabled = true;
      } else {
        button.disabled = button.dataset.wasDisabled === "true";
        delete button.dataset.wasDisabled;
      }
    }
  }

  function pulseButton(button) {
    if (!button) {
      return;
    }
    button.dataset.pressed = "true";
    const previousTimer = buttonFeedbackTimers.get(button);
    if (previousTimer) {
      window.clearTimeout(previousTimer);
    }
    const timer = window.setTimeout(() => {
      delete button.dataset.pressed;
      buttonFeedbackTimers.delete(button);
    }, 150);
    buttonFeedbackTimers.set(button, timer);
  }

  function installButtonFeedback() {
    if (buttonFeedbackInstalled) {
      return;
    }
    buttonFeedbackInstalled = true;
    document.addEventListener("pointerdown", (event) => {
      const button = event.target?.closest("button");
      if (!button || button.disabled) {
        return;
      }
      pulseButton(button);
    }, true);
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }
      const button = document.activeElement;
      if (!(button instanceof HTMLElement) || !button.matches("button") || button.disabled) {
        return;
      }
      pulseButton(button);
    }, true);
  }

  async function runButtonAction(button, action, {
    silentError = false,
    lockKey = "",
    extraBusyTargets = [],
    blockedLabel = "",
  } = {}) {
    const busyTargets = Array.from(new Set([button, ...extraBusyTargets].filter(Boolean)));
    if (busyTargets.some((target) => target?.dataset.busy === "true")) {
      if (blockedLabel) {
        renderStatusStrip([{ label: blockedLabel, variant: "warn" }]);
      }
      return null;
    }
    const normalizedLockKey = String(lockKey || "").trim();
    if (normalizedLockKey && uiActionLocks.has(normalizedLockKey)) {
      if (blockedLabel) {
        renderStatusStrip([{ label: blockedLabel, variant: "warn" }]);
      }
      return null;
    }
    if (normalizedLockKey) {
      uiActionLocks.add(normalizedLockKey);
    }
    busyTargets.forEach((target) => setButtonBusy(target, true));
    try {
      return await action();
    } catch (error) {
      console.error("按钮动作失败:", error);
      if (!silentError) {
        renderStatusStrip([{ label: error?.message || String(error), variant: "warn" }]);
      }
      return null;
    } finally {
      busyTargets.forEach((target) => setButtonBusy(target, false));
      if (normalizedLockKey) {
        uiActionLocks.delete(normalizedLockKey);
      }
    }
  }

  function bindClickAction(button, handler, {
    useBusyState = false,
    silentError = false,
    lockKey = "",
    extraBusyTargets = [],
    blockedLabel = "",
  } = {}) {
    if (!button || button.dataset.boundClickAction === "true") {
      return;
    }
    button.dataset.boundClickAction = "true";
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      if (useBusyState) {
        await runButtonAction(button, handler, {
          silentError,
          lockKey,
          extraBusyTargets,
          blockedLabel,
        });
        return;
      }
      try {
        await handler(event);
      } catch (error) {
        console.error("按钮动作失败:", error);
        if (!silentError) {
          renderStatusStrip([{ label: error?.message || String(error), variant: "warn" }]);
        }
      }
    });
  }

  return {
    bindClickAction,
    installButtonFeedback,
    runButtonAction,
    setButtonBusy,
  };
}
