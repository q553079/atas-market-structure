function normalizeString(value) {
  return String(value ?? "").trim();
}

const STABLE_SELECTOR_ATTRIBUTES = [
  "data-render-key",
  "data-message-id",
  "data-event-id",
  "data-nearby-group",
  "data-context-recipe-region",
  "data-context-recipe-block-id",
  "data-context-recipe-toggle",
  "data-context-recipe-open-trace",
  "data-answer-density",
  "data-change-inspector-region",
  "data-change-inspector-select",
  "data-change-inspector-mode",
  "data-change-inspector-pin",
  "data-change-inspector-close",
  "data-change-group",
  "data-change-record-field",
];

function isHtmlElement(node) {
  return node instanceof HTMLElement;
}

function isFocusable(node) {
  return isHtmlElement(node) && typeof node.focus === "function" && !node.hasAttribute("disabled");
}

function buildScopedChildSelector(selector = "") {
  const normalized = normalizeString(selector);
  if (!normalized) {
    return "";
  }
  return normalized
    .split(",")
    .map((part) => normalizeString(part))
    .filter(Boolean)
    .map((part) => `:scope > ${part}`)
    .join(", ");
}

function matchesSelector(node, selector = "") {
  if (!isHtmlElement(node)) {
    return false;
  }
  const normalized = normalizeString(selector);
  if (!normalized) {
    return true;
  }
  try {
    return node.matches(normalized);
  } catch {
    return false;
  }
}

function getStableSelector(node, keyAttribute = "") {
  if (!isHtmlElement(node)) {
    return "";
  }
  const attributes = [
    keyAttribute,
    ...STABLE_SELECTOR_ATTRIBUTES,
  ].filter(Boolean);
  for (const attribute of attributes) {
    const value = normalizeString(node.getAttribute(attribute));
    if (value) {
      return `[${attribute}="${CSS.escape(value)}"]`;
    }
  }
  return "";
}

function getStableKey(node, keyAttribute = "") {
  if (!isHtmlElement(node)) {
    return "";
  }
  const selector = getStableSelector(node, keyAttribute);
  const match = selector.match(/^\[(.+?)="(.+)"\]$/);
  return match?.[2] ? match[2].replace(/\\"/g, "\"") : "";
}

function ensureTemplateNode(markup = "") {
  const template = document.createElement("template");
  template.innerHTML = String(markup || "").trim();
  if (template.content.childElementCount !== 1) {
    throw new Error("render_stability: keyed patch markup must produce exactly one root element");
  }
  const node = template.content.firstElementChild;
  if (!isHtmlElement(node)) {
    throw new Error("render_stability: markup did not produce a root element");
  }
  return node;
}

function restorePreviousMarkup(container, previousMarkup, previousSignature, {
  snapshot = null,
  stateOptions = {},
  signatureAttribute = "data-render-signature",
  keyAttribute = "data-render-key",
  fallbackLabel = "restore-previous",
} = {}) {
  try {
    container.innerHTML = previousMarkup;
    if (container instanceof HTMLElement) {
      if (normalizeString(previousSignature)) {
        container.dataset.renderSignature = normalizeString(previousSignature);
      } else {
        delete container.dataset.renderSignature;
      }
      container.dataset.renderFallback = fallbackLabel;
    }
    tryRestoreContainerState(container, snapshot, {
      ...stateOptions,
      keyAttribute,
      signatureAttribute,
    }, `${fallbackLabel}:restore`);
    return false;
  } catch (restoreError) {
    reportRenderFallback(`${fallbackLabel}:restore-previous`, restoreError, {
      container: container?.tagName || null,
    });
    return false;
  }
}

function ensureKeyAttribute(node, keyAttribute, key) {
  if (!isHtmlElement(node)) {
    return node;
  }
  if (keyAttribute && !normalizeString(node.getAttribute(keyAttribute)) && key) {
    node.setAttribute(keyAttribute, key);
  }
  return node;
}

function findAnchorNode(container, selector) {
  if (!isHtmlElement(container) || !selector) {
    return null;
  }
  const containerRect = container.getBoundingClientRect();
  const nodes = container.querySelectorAll(selector);
  for (const node of nodes) {
    if (!isHtmlElement(node)) {
      continue;
    }
    const rect = node.getBoundingClientRect();
    if (rect.bottom >= containerRect.top + 4) {
      return {
        key: getStableKey(node),
        selector: getStableSelector(node),
        offset: rect.top - containerRect.top,
      };
    }
  }
  return null;
}

function captureFocusSnapshot(container, keyAttribute = "") {
  const activeElement = document.activeElement;
  if (!isHtmlElement(container) || !isHtmlElement(activeElement) || !container.contains(activeElement)) {
    return null;
  }
  const owner = activeElement.closest?.(
    [
      keyAttribute ? `[${keyAttribute}]` : "",
      "[data-render-key]",
      "[data-message-id]",
      "[data-event-id]",
      "[data-nearby-group]",
      "[data-context-recipe-region]",
      "[data-change-inspector-region]",
      "[data-context-recipe-block-id]",
      "[data-context-recipe-toggle]",
      "[data-context-recipe-open-trace]",
      "[data-answer-density]",
      "[data-change-inspector-select]",
      "[data-change-inspector-mode]",
      "[data-change-inspector-pin]",
      "[data-change-inspector-close]",
      "[data-change-group]",
      "[data-change-record-field]",
    ].filter(Boolean).join(", "),
  ) || activeElement;
  const ownerSelector = getStableSelector(owner, keyAttribute);
  if (!ownerSelector) {
    return null;
  }
  return {
    ownerSelector,
    elementSelector: getStableSelector(activeElement, keyAttribute),
  };
}

export function captureContainerState(container, {
  keyAttribute = "data-render-key",
  anchorSelector = "",
  detailsSelector = "details[data-render-key], details[data-nearby-group]",
} = {}) {
  if (!isHtmlElement(container)) {
    return null;
  }
  const resolvedAnchorSelector = anchorSelector || [
    keyAttribute ? `[${keyAttribute}]` : "",
    "[data-render-key]",
    "[data-message-id]",
    "[data-event-id]",
  ].filter(Boolean).join(", ");
  const anchor = findAnchorNode(container, resolvedAnchorSelector);
  const scrollHeight = container.scrollHeight || 0;
  const clientHeight = container.clientHeight || 0;
  const scrollTop = container.scrollTop || 0;
  const maxScrollTop = Math.max(scrollHeight - clientHeight, 0);
  const openDetailSelectors = Array.from(container.querySelectorAll(detailsSelector))
    .filter((node) => node instanceof HTMLDetailsElement && node.open === true)
    .map((node) => getStableSelector(node, keyAttribute))
    .filter(Boolean);
  return {
    scrollTop,
    nearBottom: maxScrollTop - scrollTop <= 24,
    anchorSelector: anchor?.selector || "",
    anchorOffset: anchor?.offset ?? 0,
    openDetailSelectors,
    focusSnapshot: captureFocusSnapshot(container, keyAttribute),
  };
}

export function restoreContainerState(container, snapshot, {
  keyAttribute = "data-render-key",
  detailsSelector = "details[data-render-key], details[data-nearby-group]",
} = {}) {
  if (!isHtmlElement(container) || !snapshot) {
    return;
  }
  const openSelectors = Array.isArray(snapshot.openDetailSelectors)
    ? snapshot.openDetailSelectors
    : [];
  container.querySelectorAll(detailsSelector).forEach((node) => {
    if (node instanceof HTMLDetailsElement) {
      node.open = openSelectors.includes(getStableSelector(node, keyAttribute));
    }
  });
  let restoredAnchor = false;
  if (snapshot.anchorSelector) {
    const anchorNode = container.querySelector(snapshot.anchorSelector);
    if (isHtmlElement(anchorNode)) {
      const containerRect = container.getBoundingClientRect();
      const anchorRect = anchorNode.getBoundingClientRect();
      container.scrollTop += anchorRect.top - containerRect.top - Number(snapshot.anchorOffset || 0);
      restoredAnchor = true;
    }
  }
  if (!restoredAnchor) {
    if (snapshot.nearBottom) {
      container.scrollTop = container.scrollHeight;
    } else {
      const maxScrollTop = Math.max((container.scrollHeight || 0) - (container.clientHeight || 0), 0);
      container.scrollTop = Math.min(Number(snapshot.scrollTop || 0), maxScrollTop);
    }
  }
  const focusSelector = snapshot.focusSnapshot?.elementSelector || snapshot.focusSnapshot?.ownerSelector;
  if (focusSelector && !container.contains(document.activeElement)) {
    const target = container.querySelector(focusSelector);
    if (isFocusable(target)) {
      target.focus({ preventScroll: true });
    }
  }
}

function reportRenderFallback(operation, error, details = {}) {
  console.error(`[replay_workbench_render_stability] ${operation} failed; using safe fallback.`, {
    details,
    error,
  });
}

function tryRestoreContainerState(container, snapshot, stateOptions = {}, operation = "restoreContainerState") {
  if (!snapshot) {
    return;
  }
  try {
    restoreContainerState(container, snapshot, stateOptions);
  } catch (error) {
    reportRenderFallback(operation, error, {
      container: container?.tagName || null,
    });
  }
}

export function queueEnterTransition(node, className = "is-render-entering") {
  if (!isHtmlElement(node)) {
    return;
  }
  node.classList.add(className);
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      node.classList.remove(className);
    });
  });
}

export function updateRegionMarkup(element, markup, signature = "", {
  preserveState = false,
  stateOptions = {},
  enterAnimation = false,
} = {}) {
  if (!isHtmlElement(element)) {
    return false;
  }
  const nextSignature = normalizeString(signature);
  if (element.dataset.renderSignature === nextSignature) {
    return false;
  }
  const nextMarkup = String(markup || "");
  const previousMarkup = element.innerHTML;
  const previousSignature = normalizeString(element.dataset.renderSignature);
  const snapshot = preserveState ? captureContainerState(element, stateOptions) : null;
  try {
    element.innerHTML = nextMarkup;
    element.dataset.renderSignature = nextSignature;
    delete element.dataset.renderFallback;
    tryRestoreContainerState(element, snapshot, stateOptions, "updateRegionMarkup:restore");
    if (enterAnimation) {
      Array.from(element.children).forEach((child) => queueEnterTransition(child));
    }
    return true;
  } catch (error) {
    reportRenderFallback("updateRegionMarkup", error, {
      signature: nextSignature,
      preserveState,
    });
    try {
      element.innerHTML = nextMarkup;
      element.dataset.renderSignature = nextSignature;
      element.dataset.renderFallback = "full-region";
      tryRestoreContainerState(element, snapshot, stateOptions, "updateRegionMarkup:fallback-restore");
      return true;
    } catch (fallbackError) {
      reportRenderFallback("updateRegionMarkup:fallback", fallbackError, {
        signature: nextSignature,
      });
      return restorePreviousMarkup(element, previousMarkup, previousSignature, {
        snapshot,
        stateOptions,
        fallbackLabel: "restore-previous-region",
      });
    }
  }
}

export function reconcileKeyedChildren(container, items = [], {
  keyAttribute = "data-render-key",
  signatureAttribute = "data-render-signature",
  itemSelector = "",
  preserveState = false,
  stateOptions = {},
  enterAnimationClass = "is-render-entering",
} = {}) {
  if (!isHtmlElement(container)) {
    return false;
  }
  const safeItems = Array.isArray(items) ? items : [];
  const selector = itemSelector || [
    keyAttribute ? `[${keyAttribute}]` : "",
    "[data-render-key]",
  ].filter(Boolean).join(", ");
  const scopedSelector = buildScopedChildSelector(selector);
  const previousMarkup = container.innerHTML;
  const previousSignature = normalizeString(container.dataset.renderSignature);
  const snapshot = preserveState ? captureContainerState(container, stateOptions) : null;
  try {
    const existingByKey = new Map();
    container.querySelectorAll(scopedSelector).forEach((node) => {
      const key = getStableKey(node, keyAttribute);
      if (key) {
        existingByKey.set(key, node);
      }
    });
    const desiredKeys = new Set();
    const staleNodes = new Set();
    const desiredNodes = safeItems.map((item) => {
      const key = normalizeString(item?.key);
      const signature = normalizeString(item?.signature);
      if (!key) {
        return null;
      }
      if (desiredKeys.has(key)) {
        throw new Error(`render_stability: duplicate keyed child "${key}"`);
      }
      desiredKeys.add(key);
      const existingNode = existingByKey.get(key);
      if (
        isHtmlElement(existingNode)
        && normalizeString(existingNode.getAttribute(signatureAttribute)) === signature
      ) {
        return existingNode;
      }
      if (isHtmlElement(existingNode)) {
        staleNodes.add(existingNode);
      }
      const nextNode = ensureKeyAttribute(ensureTemplateNode(item?.markup || ""), keyAttribute, key);
      if (!matchesSelector(nextNode, selector)) {
        throw new Error(`render_stability: keyed patch root does not match expected selector (${selector || keyAttribute || "item"})`);
      }
      nextNode.setAttribute(signatureAttribute, signature);
      queueEnterTransition(nextNode, enterAnimationClass);
      return nextNode;
    }).filter(isHtmlElement);
    let cursor = container.firstElementChild;
    desiredNodes.forEach((node) => {
      if (node === cursor) {
        cursor = cursor?.nextElementSibling || null;
        return;
      }
      container.insertBefore(node, cursor);
    });
    Array.from(container.querySelectorAll(scopedSelector)).forEach((node) => {
      const key = getStableKey(node, keyAttribute);
      if (staleNodes.has(node) || (key && !desiredKeys.has(key))) {
        node.remove();
      }
    });
    delete container.dataset.renderFallback;
    tryRestoreContainerState(container, snapshot, stateOptions, "reconcileKeyedChildren:restore");
    return true;
  } catch (error) {
    reportRenderFallback("reconcileKeyedChildren", error, {
      keyAttribute,
      itemCount: safeItems.length,
    });
    return restorePreviousMarkup(container, previousMarkup, previousSignature, {
      snapshot,
      stateOptions,
      signatureAttribute,
      keyAttribute,
      fallbackLabel: "restore-previous-list",
    });
  }
}
