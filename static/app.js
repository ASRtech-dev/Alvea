/**
 * ALVEA v3.0 — Process Architecture & Intelligence Studio
 * Vanilla JS client (English default, zero presets, CSP strict 'self', zero innerHTML XSS).
 */
(() => {
  "use strict";

  // ─── 1. Application State ──────────────────────────────────────────────────
  const state = {
    providers: [],
    currentProvider: "native_python",
    currentModel: "alvea-bpa-v3",
    direction: "LR",
    highlightCritical: false,
    currentMermaid: "",
    currentGraph: null,
    currentAnalytics: null,
    currentReport: null,
    currentMeta: null,
    activeTab: "visual",
    apiKeys: {},        // Browser RAM by default (optional sessionStorage)
    customUrls: {},
    persistSession: false,
    allowNativeFallback: true,
    zoom: 1,
    panX: 0,
    panY: 0,
    isDragging: false,
    dragStartX: 0,
    dragStartY: 0,
    history: [],        // Up to 30 immutable snapshots
    historyIndex: -1,
    systemPromptText: "",
  };

  // ─── 2. DOM References ─────────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const el = {
    backendBadge: $("backend-badge"),
    btnUndo: $("btn-undo"),
    btnRedo: $("btn-redo"),
    btnHistory: $("btn-history"),
    historyCount: $("history-count"),
    btnConfigAi: $("btn-config-ai"),
    btnViewPrompt: $("btn-view-prompt"),
    btnOpenDocs: $("btn-open-docs"),
    btnShortcuts: $("btn-shortcuts"),
    btnThemeToggle: $("btn-theme-toggle"),
    themeLabel: $("theme-label"),

    processDescription: $("process-description"),
    charCounter: $("char-counter"),
    btnClearText: $("btn-clear-text"),
    providerSelect: $("provider-select"),
    modelSelect: $("model-select"),
    btnDiscoverModels: $("btn-discover-models"),
    providerBadges: $("provider-badges"),
    providerNote: $("provider-note"),
    credentialStatus: $("credential-status"),
    chkCriticalPath: $("chk-critical-path"),
    btnGenerate: $("btn-generate"),
    btnGenerateLabel: $("btn-generate-label"),

    actorChipsContainer: $("actor-chips-container"),
    cognitiveDecisionsList: $("cognitive-decisions-list"),
    cognitiveRoutesText: $("cognitive-routes-text"),

    tabButtons: Array.from(document.querySelectorAll(".tab-btn")),
    viewVisual: $("view-visual"),
    viewEditor: $("view-editor"),
    viewReport: $("view-report"),
    viewData: $("view-data"),
    viewDocs: $("view-docs"),
    docsMainHeading: $("docs-main-heading"),

    canvasEmptyState: $("canvas-empty-state"),
    btnEmptyFocus: $("btn-empty-focus"),
    btnEmptyDocs: $("btn-empty-docs"),
    inputEmptyImportYaml: $("input-empty-import-yaml"),

    metricsStrip: $("metrics-strip"),
    kpiGrade: $("kpi-grade"),
    kpiLanes: $("kpi-lanes"),
    kpiNodes: $("kpi-nodes"),
    kpiComplexity: $("kpi-complexity"),
    kpiAuto: $("kpi-auto"),
    kpiCycles: $("kpi-cycles"),
    kpiCritical: $("kpi-critical"),
    kpiBottleneck: $("kpi-bottleneck"),

    diagramViewport: $("diagram-viewport"),
    mermaidTarget: $("mermaid-target"),
    mermaidCodeInput: $("mermaid-code-input"),
    validationBanner: $("validation-banner"),
    btnRepairEditor: $("btn-repair-editor"),
    btnApplyEditor: $("btn-apply-editor"),
    reportContainer: $("report-container"),
    dataPreview: $("data-preview"),

    btnZoomOut: $("btn-zoom-out"),
    btnZoomIn: $("btn-zoom-in"),
    btnZoomReset: $("btn-zoom-reset"),
    btnZoomFit: $("btn-zoom-fit"),
    zoomLabel: $("zoom-label"),
    btnCopyMermaid: $("btn-copy-mermaid"),
    btnExportSvg: $("btn-export-svg"),
    btnExportPng: $("btn-export-png"),
    btnExportPdf: $("btn-export-pdf"),
    btnExportYaml: $("btn-export-yaml"),
    btnDownloadJson: $("btn-download-json"),
    btnDownloadYaml2: $("btn-download-yaml-2"),
    inputImportYaml: $("input-import-yaml"),
    btnFullscreen: $("btn-fullscreen"),

    statusDot: $("status-dot"),
    statusText: $("status-text"),
    telemetryText: $("telemetry-text"),

    modalAi: $("modal-ai"),
    modalProviderSelect: $("modal-provider-select"),
    modalApiKeyGroup: $("modal-apikey-group"),
    modalApiKey: $("modal-api-key"),
    btnToggleKey: $("btn-toggle-key"),
    modalBaseUrlGroup: $("modal-baseurl-group"),
    modalBaseUrl: $("modal-base-url"),
    chkSessionPersist: $("chk-session-persist"),
    chkNativeFallback: $("chk-native-fallback"),
    btnClearProviderKey: $("btn-clear-provider-key"),
    btnSaveProviderCfg: $("btn-save-provider-cfg"),

    modalPrompt: $("modal-prompt"),
    promptContent: $("prompt-content"),
    btnCopyPrompt: $("btn-copy-prompt"),

    modalHistory: $("modal-history"),
    historyList: $("history-list"),

    modalShortcuts: $("modal-shortcuts"),
    toastContainer: $("toast-container"),
  };

  // ─── 3. XSS-Safe DOM Helpers ───────────────────────────────────────────────
  function h(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, val] of Object.entries(props || {})) {
      if (val === undefined || val === null || val === false) continue;
      if (key === "className") {
        node.className = String(val);
      } else if (key === "text") {
        node.textContent = String(val);
      } else if (key.startsWith("on") && typeof val === "function") {
        node.addEventListener(key.slice(2).toLowerCase(), val);
      } else {
        node.setAttribute(key, String(val));
      }
    }
    for (const child of children.flat()) {
      if (child === undefined || child === null || child === false) continue;
      node.appendChild(
        typeof child === "string" || typeof child === "number"
          ? document.createTextNode(String(child))
          : child
      );
    }
    return node;
  }

  function safeSetHTML(targetEl, rawHtml) {
    const allowedElements = ["p", "b", "i", "strong", "em", "code", "ul", "li", "span"];
    if ("setHTML" in Element.prototype) {
      targetEl.setHTML(rawHtml, { sanitizer: { elements: allowedElements, attributes: ["class"] } });
      return;
    }
    const parser = new DOMParser();
    const doc = parser.parseFromString(String(rawHtml || ""), "text/html");
    const allowSet = new Set(allowedElements);
    const cleanNode = (src) => {
      if (src.nodeType === Node.TEXT_NODE) return document.createTextNode(src.textContent || "");
      if (src.nodeType !== Node.ELEMENT_NODE) return null;
      const tag = src.tagName.toLowerCase();
      if (!allowSet.has(tag)) return null;
      const copy = document.createElement(tag);
      const cls = src.getAttribute("class");
      if (cls) copy.setAttribute("class", cls);
      for (const ch of src.childNodes) {
        const cleaned = cleanNode(ch);
        if (cleaned) copy.appendChild(cleaned);
      }
      return copy;
    };
    const frag = document.createDocumentFragment();
    for (const ch of doc.body.childNodes) {
      const cleaned = cleanNode(ch);
      if (cleaned) frag.appendChild(cleaned);
    }
    targetEl.replaceChildren(frag);
  }

  function safeMountSvg(container, svgMarkup) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(svgMarkup, "image/svg+xml");
    const svgEl = doc.documentElement;
    if (!svgEl || svgEl.tagName.toLowerCase() !== "svg") {
      throw new Error("Mermaid renderer did not return a valid SVG element.");
    }
    svgEl.querySelectorAll("script, iframe, object, embed, foreignObject").forEach((n) => n.remove());
    [svgEl, ...svgEl.querySelectorAll("*")].forEach((elem) => {
      for (const attr of Array.from(elem.attributes)) {
        const name = attr.name.toLowerCase();
        const val = attr.value.replace(/[\x00-\x20]+/g, "").toLowerCase();
        if (
          name.startsWith("on") ||
          val.startsWith("javascript:") ||
          val.startsWith("vbscript:") ||
          val.startsWith("data:text/html")
        ) {
          elem.removeAttribute(attr.name);
        }
      }
    });
    container.replaceChildren(document.importNode(svgEl, true));
  }

  // ─── 4. Theme Toggle (System / Light / Dark) ───────────────────────────────
  function getStoredScheme() {
    try {
      const val = localStorage.getItem("alvea_color_scheme");
      return val === "light" || val === "dark" ? val : "system";
    } catch (_) {
      return "system";
    }
  }

  function applyColorScheme(mode, persist = true) {
    const meta = document.querySelector('meta[name="color-scheme"]');
    if (meta) {
      meta.content = mode === "light" || mode === "dark" ? mode : "light dark";
    }
    if (persist) {
      try {
        if (mode === "system") localStorage.removeItem("alvea_color_scheme");
        else localStorage.setItem("alvea_color_scheme", mode);
      } catch (_) {
        /* Ignore storage errors */
      }
    }
    const labels = { system: "System", light: "Light", dark: "Dark" };
    el.themeLabel.textContent = labels[mode] || "System";
  }

  function cycleColorScheme() {
    const order = ["system", "light", "dark"];
    const next = order[(order.indexOf(getStoredScheme()) + 1) % order.length];
    applyColorScheme(next, true);
    showToast(`Theme switched to ${next === "system" ? "System" : next === "dark" ? "Dark" : "Light"}.`);
  }

  // ─── 5. Top-Layer Dialog Enhancements & Fallbacks ──────────────────────────
  let supportsDisplayTransition;
  function canTransitionDisplay() {
    if (supportsDisplayTransition !== undefined) return supportsDisplayTransition;
    if (!window.CSS?.supports?.("transition-behavior", "allow-discrete") || !document.body) return false;
    const probe = document.createElement("div");
    probe.style.cssText = "transition: display 1s allow-discrete !important; display: block;";
    document.body.appendChild(probe);
    getComputedStyle(probe).display;
    probe.style.display = "none";
    supportsDisplayTransition = getComputedStyle(probe).display === "block";
    probe.remove();
    return supportsDisplayTransition;
  }

  function supportsTopLayerExit() {
    return Boolean(window.CSS?.supports?.("overlay", "auto") && canTransitionDisplay());
  }

  function openTopLayer(dialog) {
    if (!dialog) return;
    dialog.removeAttribute("data-closing");
    if (!dialog.open) dialog.showModal();
  }

  async function closeTopLayer(dialog) {
    if (!dialog || !dialog.open) return;
    if (!supportsTopLayerExit()) {
      dialog.setAttribute("data-closing", "");
      const animations = dialog.getAnimations({ subtree: true });
      if (animations.length > 0) {
        await Promise.race([
          Promise.allSettled(animations.map((a) => a.finished)),
          new Promise((r) => setTimeout(r, 400)),
        ]);
      }
      if (!dialog.hasAttribute("data-closing")) return;
      dialog.removeAttribute("data-closing");
    }
    dialog.close();
  }

  function setupDialogEnhancements(dialog) {
    dialog.addEventListener("cancel", (event) => {
      if (!supportsTopLayerExit()) {
        event.preventDefault();
        closeTopLayer(dialog);
      }
    });

    if (!("closedBy" in HTMLDialogElement.prototype)) {
      dialog.addEventListener("click", (event) => {
        if (event.target !== dialog) return;
        const rect = dialog.getBoundingClientRect();
        const inside =
          rect.top <= event.clientY &&
          event.clientY <= rect.top + rect.height &&
          rect.left <= event.clientX &&
          event.clientX <= rect.left + rect.width;
        if (!inside) closeTopLayer(dialog);
      });
    }
  }

  // ─── 6. Credentials (RAM / Optional sessionStorage) ────────────────────────
  function loadSessionCredentials() {
    try {
      const enabled = sessionStorage.getItem("alvea_persist_session") === "1";
      state.persistSession = enabled;
      el.chkSessionPersist.checked = enabled;
      if (enabled) {
        state.apiKeys = JSON.parse(sessionStorage.getItem("alvea_session_keys") || "{}");
        state.customUrls = JSON.parse(sessionStorage.getItem("alvea_session_urls") || "{}");
      }
    } catch (_) {
      state.apiKeys = {};
      state.customUrls = {};
    }
  }

  function syncSessionCredentials() {
    try {
      if (state.persistSession) {
        sessionStorage.setItem("alvea_persist_session", "1");
        sessionStorage.setItem("alvea_session_keys", JSON.stringify(state.apiKeys));
        sessionStorage.setItem("alvea_session_urls", JSON.stringify(state.customUrls));
      } else {
        sessionStorage.removeItem("alvea_persist_session");
        sessionStorage.removeItem("alvea_session_keys");
        sessionStorage.removeItem("alvea_session_urls");
      }
    } catch (_) {
      /* Ignore */
    }
  }

  // ─── 7. Initialization (Clean Empty Canvas, Zero Presets) ──────────────────
  async function init() {
    applyColorScheme(getStoredScheme(), false);
    window.addEventListener("storage", (e) => {
      if (e.key === "alvea_color_scheme") applyColorScheme(getStoredScheme(), false);
    });

    [el.modalAi, el.modalPrompt, el.modalHistory, el.modalShortcuts].forEach(setupDialogEnhancements);
    loadSessionCredentials();
    initMermaid();
    bindEvents();
    setDiagramControlsEnabled(false);

    await Promise.all([loadHealth(), loadProviders()]);
    setStatus("ok", "Ready — Enter a workflow or open Guide to begin.");
  }

  function initMermaid() {
    if (typeof window.mermaid === "undefined") {
      setStatus("error", "Could not load local vendor/mermaid.min.js.");
      return;
    }
    window.mermaid.initialize({
      startOnLoad: false,
      theme: "default",
      securityLevel: "strict",
      htmlLabels: false,
      flowchart: {
        curve: "basis",
        useMaxWidth: false,
        htmlLabels: false,
        padding: 18,
      },
    });
  }

  function setDiagramControlsEnabled(enabled) {
    [
      el.btnZoomOut,
      el.btnZoomIn,
      el.btnZoomReset,
      el.btnZoomFit,
      el.btnCopyMermaid,
      el.btnExportSvg,
      el.btnExportPng,
      el.btnExportPdf,
      el.btnExportYaml,
      el.btnDownloadJson,
      el.btnDownloadYaml2,
      el.btnFullscreen,
    ].forEach((btn) => {
      if (btn) btn.disabled = !enabled;
    });
    el.canvasEmptyState.hidden = enabled;
    el.diagramViewport.hidden = !enabled;
    el.viewVisual.classList.toggle("canvas-pane--empty", !enabled);
    el.metricsStrip.classList.toggle("metrics-strip--empty", !enabled);
  }

  // ─── 8. Backend Health & Provider Catalog ──────────────────────────────────
  async function loadHealth() {
    try {
      const resp = await fetch("/api/v1/health");
      if (resp.ok) {
        const data = await resp.json();
        el.backendBadge.textContent = `Python v${data.version} · NetworkX`;
        return;
      }
    } catch (_) {
      /* Offline fallback */
    }
    el.backendBadge.textContent = "Backend Offline";
  }

  async function loadProviders() {
    try {
      const resp = await fetch("/api/v1/providers");
      if (!resp.ok) throw new Error("Failed to load provider catalog.");
      const data = await resp.json();
      state.providers = data.providers || [];
      populateProviderSelects();
      selectProvider("native_python");
    } catch (err) {
      showToast(err.message, true);
    }
  }

  function populateProviderSelects() {
    const groups = [
      { key: "local", label: "Local · Zero API Key (Private)" },
      { key: "free_cloud", label: "Free Cloud Tiers (2026 Multi-Vendor)" },
      { key: "byok", label: "Other Providers / Custom (BYOK)" },
    ];

    const buildSelect = (selectEl) => {
      selectEl.replaceChildren();
      for (const grp of groups) {
        const items = state.providers.filter((p) => p.group === grp.key);
        if (!items.length) continue;
        const optgroup = h("optgroup", { label: grp.label });
        for (const p of items) {
          optgroup.appendChild(h("option", { value: p.id, text: `${p.name} — ${p.company}` }));
        }
        selectEl.appendChild(optgroup);
      }
    };

    buildSelect(el.providerSelect);
    buildSelect(el.modalProviderSelect);
  }

  function getProviderSpec(id) {
    return state.providers.find((p) => p.id === id) || null;
  }

  function selectProvider(providerId) {
    const spec = getProviderSpec(providerId) || state.providers[0];
    if (!spec) return;
    state.currentProvider = spec.id;
    el.providerSelect.value = spec.id;

    el.modelSelect.replaceChildren();
    (spec.models || []).forEach((m) => {
      const badgeSuffix = m.badges && m.badges.length ? ` [${m.badges.join(" · ")}]` : "";
      el.modelSelect.appendChild(h("option", { value: m.id, text: `${m.label}${badgeSuffix}` }));
    });
    state.currentModel = spec.default_model || (spec.models[0] ? spec.models[0].id : "");
    el.modelSelect.value = state.currentModel;

    el.btnDiscoverModels.hidden = !spec.supports_discovery;

    el.providerBadges.replaceChildren();
    (spec.badges || []).forEach((b) => {
      const low = b.toLowerCase();
      let cls = "badge badge--subtle";
      if (low.includes("local") || low.includes("no api") || low.includes("offline")) cls = "badge badge--local";
      else if (low.includes("free")) cls = "badge badge--free";
      else if (low.includes("fast") || low.includes("lpu")) cls = "badge badge--fast";
      el.providerBadges.appendChild(h("span", { className: cls, text: b }));
    });

    el.providerNote.textContent = spec.privacy_note || "";
    updateCredentialStatus(spec);
  }

  function updateCredentialStatus(spec) {
    if (!spec) return;
    if (!spec.requires_api_key) {
      el.credentialStatus.textContent = "No key required";
      el.credentialStatus.className = "credential-pill credential-pill--ok";
      return;
    }
    const hasKey = Boolean(state.apiKeys[spec.id]);
    if (hasKey) {
      el.credentialStatus.textContent = "Key ready (RAM)";
      el.credentialStatus.className = "credential-pill credential-pill--ok";
    } else {
      el.credentialStatus.textContent = "API key required";
      el.credentialStatus.className = "credential-pill credential-pill--warn";
    }
  }

  async function discoverLocalModels() {
    const spec = getProviderSpec(state.currentProvider);
    if (!spec || !spec.supports_discovery) return;

    el.btnDiscoverModels.disabled = true;
    el.btnDiscoverModels.textContent = "Scanning…";
    try {
      const headers = {};
      if (state.customUrls[spec.id]) headers["X-Provider-Base-Url"] = state.customUrls[spec.id];
      const resp = await fetch(`/api/v1/providers/${encodeURIComponent(spec.id)}/models`, { headers });
      const data = await resp.json();
      if (!data.ok || !data.models.length) {
        showToast(data.detail || "No local models detected.", true);
        return;
      }
      const prevModel = el.modelSelect.value;
      el.modelSelect.replaceChildren();
      data.models.forEach((m) => {
        el.modelSelect.appendChild(h("option", { value: m.id, text: m.label }));
      });
      if (data.models.some((m) => m.id === prevModel)) el.modelSelect.value = prevModel;
      state.currentModel = el.modelSelect.value;
      showToast(data.detail);
    } catch (_) {
      showToast("Failed to probe local model server.", true);
    } finally {
      el.btnDiscoverModels.disabled = false;
      el.btnDiscoverModels.textContent = "Auto-Discover";
    }
  }

  // ─── 9. Workflow Generation, Validation & Rendering ────────────────────────
  async function runGeneration() {
    const text = el.processDescription.value.trim();
    if (text.length < 5) {
      showToast("Please enter a workflow description (at least 5 characters).", true);
      el.processDescription.focus();
      return;
    }

    const providerId = state.currentProvider;
    const spec = getProviderSpec(providerId);
    const modelId = el.modelSelect.value;

    if (spec && spec.requires_api_key && !state.apiKeys[providerId]) {
      openAiModal(providerId);
      showToast(`Configure your API key for ${spec.name} (or switch to a Local engine).`, true);
      return;
    }

    setBusy(true, `Analyzing workflow with ${spec ? spec.name : providerId}…`);
    try {
      const headers = { "Content-Type": "application/json" };
      if (state.apiKeys[providerId]) headers["X-API-Key"] = state.apiKeys[providerId];

      const resp = await fetch("/api/v1/generate", {
        method: "POST",
        headers,
        body: JSON.stringify({
          text,
          provider: providerId,
          model: modelId,
          direction: state.direction,
          highlight_critical: state.highlightCritical,
          base_url: state.customUrls[providerId] || null,
          allow_native_fallback: state.allowNativeFallback,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || `HTTP error ${resp.status}`);

      if (state.activeTab === "docs") switchTab("visual");
      await applyPipelineResult(data, { pushHistory: true, label: data.graph?.title || "Generated Workflow" });
      if (data.meta?.fallback_notice) {
        showToast(data.meta.fallback_notice, true);
      } else {
        showToast(`Workflow architecture generated (${data.meta?.elapsed_ms ?? 0} ms).`);
      }
    } catch (err) {
      setStatus("error", err.message || "Failed to generate workflow.");
      showToast(err.message || "Failed to generate workflow.", true);
    } finally {
      setBusy(false);
    }
  }

  async function validateAndApplyMermaid(code, { direction = null, pushHistory = true, label = "Manual edit" } = {}) {
    if (!code || !code.trim()) return;
    setBusy(true, "Validating Mermaid syntax and recalculating NetworkX…");
    try {
      const resp = await fetch("/api/v1/mermaid/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code,
          direction,
          highlight_critical: state.highlightCritical,
          auto_repair: true,
          title: state.currentGraph?.title || null,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || `HTTP error ${resp.status}`);
      await applyPipelineResult(data, { pushHistory, label });
      renderValidationBanner(data.validation);
      showToast("Diagram and NetworkX analytics updated.");
    } catch (err) {
      setStatus("error", err.message);
      showToast(err.message, true);
    } finally {
      setBusy(false);
    }
  }

  async function applyPipelineResult(data, { pushHistory = true, label = "Snapshot" } = {}) {
    state.currentMermaid = data.mermaid || "";
    state.currentGraph = data.graph || null;
    state.currentAnalytics = data.analytics || null;
    state.currentReport = data.report || null;
    state.currentMeta = data.meta || null;

    setDiagramControlsEnabled(Boolean(state.currentMermaid));
    el.mermaidCodeInput.value = state.currentMermaid;
    renderValidationBanner(data.validation);
    renderMetricsStrip(state.currentAnalytics);
    renderCognitivePanel(state.currentReport?.cognitive);
    renderExecutiveReport(state.currentReport, state.currentAnalytics);
    renderDataPreview();

    await renderMermaidSvg(state.currentMermaid);

    if (pushHistory) pushSnapshot(label);

    const meta = state.currentMeta || {};
    el.telemetryText.textContent = `${meta.provider_name || "ALVEA"} · ${meta.model || ""} · ${meta.elapsed_ms ?? 0} ms · graph ${state.direction}`;
    setStatus("ok", "Architecture rendered and audited with NetworkX.");
  }

  async function renderMermaidSvg(code) {
    if (typeof window.mermaid === "undefined" || !code) return;
    try {
      const normalized = String(code).replace(/<br\s*\/?>/gi, "\\n");
      const uid = "alvea_svg_" + Math.random().toString(36).slice(2, 9);
      const { svg } = await window.mermaid.render(uid, normalized);
      safeMountSvg(el.mermaidTarget, svg);
      resetZoom();
      requestAnimationFrame(() => fitZoom());
    } catch (err) {
      const box = h(
        "div",
        { className: "mermaid-error-box" },
        h("h3", { className: "mermaid-error-title", text: "Mermaid Syntax Error" }),
        h("p", { className: "mermaid-error-msg", text: err.message || "Invalid diagram syntax." }),
        h("button", {
          className: "btn btn-outline btn-sm",
          type: "button",
          text: "Restore Last Valid Version",
          onClick: () => restoreLastValidSnapshot(),
        })
      );
      el.mermaidTarget.replaceChildren(box);
      setStatus("error", "Mermaid rendering error.");
    }
  }

  // ─── 10. Metrics, Cognitive Panel & Executive Report (Zero XSS) ────────────
  function renderValidationBanner(validation) {
    if (!validation || (!validation.warnings?.length && !validation.repairs_applied?.length)) {
      el.validationBanner.hidden = true;
      el.validationBanner.textContent = "";
      return;
    }
    const items = [...(validation.warnings || []), ...(validation.repairs_applied || [])];
    el.validationBanner.hidden = false;
    el.validationBanner.textContent = `Validation / Auto-Repair: ${items.join(" · ")}`;
  }

  function formatMinutes(min) {
    if (min >= 480) return `${(min / 480).toFixed(1)}d`;
    if (min >= 60) {
      const hrs = Math.floor(min / 60);
      const rem = Math.round(min % 60);
      return rem ? `${hrs}h ${rem}m` : `${hrs}h`;
    }
    return `${Math.round(min)}m`;
  }

  function renderMetricsStrip(a) {
    if (!a) return;
    el.kpiGrade.textContent = a.efficiency_grade || "—";
    el.kpiLanes.textContent = String(a.lane_count ?? 0);
    el.kpiNodes.textContent = `${a.node_count ?? 0} / ${a.edge_count ?? 0}`;
    el.kpiComplexity.textContent = `M=${a.cyclomatic_complexity ?? 1} (${a.complexity_level || "Low"})`;
    el.kpiAuto.textContent = `${Math.round((a.automation_ratio || 0) * 100)}%`;
    el.kpiCycles.textContent = String((a.cycles || []).length);
    const steps = (a.critical_path || []).length;
    el.kpiCritical.textContent =
      a.estimated_cycle_time_min != null ? `${steps} steps · ${formatMinutes(a.estimated_cycle_time_min)}` : `${steps} steps`;
    const topBn = (a.bottlenecks || [])[0];
    el.kpiBottleneck.textContent = topBn ? `${topBn.label} (${topBn.risk_score.toFixed(2)})` : "None critical";
    el.kpiBottleneck.title = topBn ? `${topBn.label} — ${topBn.lane_name}` : "";
  }

  function renderCognitivePanel(cog) {
    if (!cog) return;
    el.actorChipsContainer.replaceChildren(
      ...(cog.phase_a_actors || []).map((a) =>
        h("span", { className: "actor-chip", text: `${a.name} (${a.nodes})` })
      )
    );
    el.cognitiveDecisionsList.replaceChildren(
      ...(cog.phase_b_decisions || []).map((d) => h("li", { text: d }))
    );
    el.cognitiveRoutesText.textContent = cog.phase_c_routes || "";
  }

  function renderExecutiveReport(report, analytics) {
    if (!report || !analytics) return;

    const laneRows = (report.lane_breakdown || []).map((lm) =>
      h(
        "tr",
        {},
        h("td", { text: lm.lane_name }),
        h("td", { text: lm.kind }),
        h("td", { className: "tabular-nums", text: String(lm.node_count) }),
        h("td", { className: "tabular-nums", text: `${lm.workload_pct}%` }),
        h("td", { className: "tabular-nums", text: `${lm.handoffs_in} / ${lm.handoffs_out}` })
      )
    );

    const bottleneckItems = (report.bottleneck_findings || []).map((f) =>
      h("li", { className: "report-card-item", text: f })
    );
    const reworkItems = (report.rework_findings || []).map((f) =>
      h("li", { className: "report-card-item", text: f })
    );
    const recItems = (report.recommendations || []).map((r) =>
      h(
        "li",
        { className: "report-card-item" },
        h("strong", { text: `[${r.priority} · ${r.category}] ${r.title}: ` }),
        r.detail
      )
    );

    const cpText = (analytics.critical_path_labels || []).join(" → ") || "Not computable";
    const cpUnit =
      analytics.estimated_cycle_time_min != null
        ? formatMinutes(analytics.estimated_cycle_time_min)
        : `${analytics.critical_path_weight} pts`;

    const docNodes = [
      h(
        "div",
        { className: "report-header" },
        h(
          "div",
          {},
          h("h2", { className: "report-title", text: report.title }),
          h("p", {
            className: "provider-note",
            text: `Live NetworkX Diagnostics · ${analytics.lane_count} swimlanes · ${analytics.node_count} nodes · ${analytics.complexity_level} complexity`,
          })
        ),
        h("div", { className: "report-grade-badge tabular-nums", text: `Grade ${report.efficiency_grade}` })
      ),
      h(
        "section",
        { className: "report-section" },
        h("h3", { text: "1. Executive Diagnosis" }),
        h("p", { text: report.summary })
      ),
      h(
        "section",
        { className: "report-section" },
        h("h3", { text: "2. Workload Distribution by Swimlane" }),
        h(
          "table",
          { className: "report-table" },
          h(
            "thead",
            {},
            h(
              "tr",
              {},
              h("th", { text: "Swimlane / Actor" }),
              h("th", { text: "Kind" }),
              h("th", { text: "Nodes" }),
              h("th", { text: "Share" }),
              h("th", { text: "Handoffs (In/Out)" })
            )
          ),
          h("tbody", {}, ...laneRows)
        )
      ),
      h(
        "section",
        { className: "report-section" },
        h("h3", { text: "3. Critical Path & Bottlenecks (NetworkX)" }),
        h("p", { text: `Critical Path (${analytics.critical_path.length} steps · ${cpUnit}): ${cpText}` }),
        h("ul", { className: "report-list" }, ...bottleneckItems, ...reworkItems)
      ),
      h(
        "section",
        { className: "report-section" },
        h("h3", { text: "4. Actionable Recommendations" }),
        h("ul", { className: "report-list" }, ...recItems)
      ),
    ];

    if (analytics.anomalies && analytics.anomalies.length > 0) {
      docNodes.push(
        h(
          "section",
          { className: "report-section" },
          h("h3", { text: "5. Structural Anomalies Detected" }),
          h(
            "ul",
            { className: "report-list" },
            ...analytics.anomalies.map((an) =>
              h("li", { className: "report-card-item", text: `[${an.severity.toUpperCase()}] ${an.message}` })
            )
          )
        )
      );
    }

    el.reportContainer.replaceChildren(...docNodes);
  }

  function renderDataPreview() {
    if (!state.currentGraph) {
      el.dataPreview.textContent = "// Canonical ProcessGraph and NetworkX metrics will appear here after generation.";
      return;
    }
    el.dataPreview.textContent = JSON.stringify(
      { schema_version: "3.0", process_graph: state.currentGraph, analytics: state.currentAnalytics },
      null,
      2
    );
  }

  // ─── 11. Session Version History (Undo / Redo) ─────────────────────────────
  function pushSnapshot(label) {
    const snap = {
      id: Date.now().toString(36),
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
      label,
      direction: state.direction,
      description: el.processDescription.value,
      mermaid: state.currentMermaid,
      graph: state.currentGraph,
      analytics: state.currentAnalytics,
      report: state.currentReport,
      meta: state.currentMeta,
    };
    if (state.historyIndex < state.history.length - 1) {
      state.history = state.history.slice(0, state.historyIndex + 1);
    }
    state.history.push(snap);
    if (state.history.length > 30) state.history.shift();
    state.historyIndex = state.history.length - 1;
    updateHistoryButtons();
  }

  function updateHistoryButtons() {
    el.historyCount.textContent = String(state.history.length);
    el.btnUndo.disabled = state.historyIndex <= 0;
    el.btnRedo.disabled = state.historyIndex >= state.history.length - 1;
  }

  async function restoreSnapshot(index) {
    const snap = state.history[index];
    if (!snap) return;
    state.historyIndex = index;
    state.direction = snap.direction;
    syncDirectionRadios();
    el.processDescription.value = snap.description;
    updateCharCount();
    await applyPipelineResult(snap, { pushHistory: false });
    updateHistoryButtons();
    showToast(`Restored snapshot: ${snap.label} (${snap.time}).`);
  }

  function restoreLastValidSnapshot() {
    if (state.historyIndex >= 0 && state.history[state.historyIndex]) {
      restoreSnapshot(state.historyIndex);
    }
  }

  function openHistoryModal() {
    el.historyList.replaceChildren();
    if (!state.history.length) {
      el.historyList.appendChild(h("p", { className: "dialog-intro", text: "No versions recorded in this session yet." }));
    } else {
      [...state.history].reverse().forEach((snap, revIdx) => {
        const idx = state.history.length - 1 - revIdx;
        const isCurrent = idx === state.historyIndex;
        el.historyList.appendChild(
          h(
            "div",
            { className: "history-row" },
            h(
              "div",
              {},
              h("strong", { text: `${snap.label}${isCurrent ? " (Current)" : ""}` }),
              h("div", {
                className: "hint-text",
                text: `${snap.time} · graph ${snap.direction} · ${snap.analytics?.node_count ?? 0} nodes`,
              })
            ),
            h("button", {
              className: "btn btn-outline btn-xs",
              type: "button",
              disabled: isCurrent,
              text: "Restore",
              onClick: () => {
                restoreSnapshot(idx);
                closeTopLayer(el.modalHistory);
              },
            })
          )
        );
      });
    }
    openTopLayer(el.modalHistory);
  }

  // ─── 12. Reliable Exports (SVG, PNG 3x HD, PDF, YAML, JSON) ────────────────
  function buildCleanSvg(svgEl) {
    const clone = svgEl.cloneNode(true);
    clone.querySelectorAll("foreignObject, script").forEach((n) => n.remove());

    let vbX = 0;
    let vbY = 0;
    let w = 1200;
    let hVal = 600;
    const vb = svgEl.viewBox && svgEl.viewBox.baseVal;
    if (vb && vb.width > 0 && vb.height > 0) {
      vbX = vb.x;
      vbY = vb.y;
      w = Math.ceil(vb.width);
      hVal = Math.ceil(vb.height);
    } else {
      const box = svgEl.getBBox();
      vbX = box.x - 20;
      vbY = box.y - 20;
      w = Math.ceil(box.width + 40);
      hVal = Math.ceil(box.height + 40);
      clone.setAttribute("viewBox", `${vbX} ${vbY} ${w} ${hVal}`);
    }

    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    clone.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
    clone.setAttribute("width", String(w));
    clone.setAttribute("height", String(hVal));
    clone.removeAttribute("style");

    const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    bg.setAttribute("x", String(vbX));
    bg.setAttribute("y", String(vbY));
    bg.setAttribute("width", "100%");
    bg.setAttribute("height", "100%");
    bg.setAttribute("fill", "#ffffff");
    clone.insertBefore(bg, clone.firstChild);

    return { svgString: new XMLSerializer().serializeToString(clone), width: w, height: hVal };
  }

  function utf8ToBase64(str) {
    const bytes = new TextEncoder().encode(str);
    let binary = "";
    for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
    return btoa(binary);
  }

  function renderSvgToPngBlob(svgEl, desiredScale = 3) {
    return new Promise((resolve, reject) => {
      const { svgString, width, height } = buildCleanSvg(svgEl);
      const scale = Math.min(desiredScale, 8192 / Math.max(width, height, 1));
      const dataUrl = `data:image/svg+xml;base64,${utf8ToBase64(svgString)}`;

      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.round(width * scale));
        canvas.height = Math.max(1, Math.round(height * scale));
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        canvas.toBlob((blob) => {
          if (!blob) reject(new Error("Failed to encode PNG image."));
          else resolve(blob);
        }, "image/png");
      };
      img.onerror = () => reject(new Error("Failed to rasterize SVG to PNG."));
      img.src = dataUrl;
    });
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1200);
  }

  function exportAsSvg() {
    const svg = el.mermaidTarget.querySelector("svg");
    if (!svg) return showToast("Generate a diagram before exporting.", true);
    const { svgString } = buildCleanSvg(svg);
    downloadBlob(new Blob([svgString], { type: "image/svg+xml;charset=utf-8" }), "alvea_workflow.svg");
    showToast("Vector SVG downloaded.");
  }

  async function exportAsPng() {
    const svg = el.mermaidTarget.querySelector("svg");
    if (!svg) return showToast("Generate a diagram before exporting.", true);
    try {
      const blob = await renderSvgToPngBlob(svg, 3);
      downloadBlob(blob, "alvea_workflow_hd.png");
      showToast("3x HD PNG downloaded.");
    } catch (err) {
      showToast(err.message, true);
    }
  }

  async function exportAsPdf() {
    if (!state.currentMermaid) return showToast("Generate a workflow before exporting PDF.", true);
    setBusy(true, "Generating Executive PDF Report with ReportLab…");
    try {
      let pngBase64 = null;
      const svg = el.mermaidTarget.querySelector("svg");
      if (svg) {
        try {
          const blob = await renderSvgToPngBlob(svg, 2);
          if (blob.size < 1_600_000) {
            pngBase64 = await new Promise((res) => {
              const reader = new FileReader();
              reader.onloadend = () => res(reader.result);
              reader.readAsDataURL(blob);
            });
          }
        } catch (_) {
          pngBase64 = null;
        }
      }

      const resp = await fetch("/api/v1/export/pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: state.currentGraph?.title || "Executive Report",
          mermaid: state.currentMermaid,
          direction: state.direction,
          diagram_png_base64: pngBase64,
        }),
      });
      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.error || `PDF export failed (${resp.status})`);
      }
      downloadBlob(await resp.blob(), "alvea_executive_report.pdf");
      showToast("Executive PDF report downloaded.");
    } catch (err) {
      showToast(err.message, true);
    } finally {
      setBusy(false);
    }
  }

  async function exportStructured(format) {
    if (!state.currentMermaid) return showToast("Generate a workflow before exporting.", true);
    try {
      const resp = await fetch(`/api/v1/export/${format}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: state.currentGraph?.title || "Workflow",
          mermaid: state.currentMermaid,
          direction: state.direction,
        }),
      });
      if (!resp.ok) throw new Error(`Failed to export ${format.toUpperCase()}.`);
      downloadBlob(await resp.blob(), `alvea_workflow.${format}`);
      showToast(`${format.toUpperCase()} file downloaded.`);
    } catch (err) {
      showToast(err.message, true);
    }
  }

  async function handleImportYaml(file) {
    if (!file) return;
    try {
      const yamlContent = await file.text();
      const resp = await fetch("/api/v1/import/yaml", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ yaml_content: yamlContent }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || "Failed to import YAML.");
      await applyPipelineResult(
        {
          ...data,
          validation: { is_valid: true, warnings: [], repairs_applied: [] },
          meta: { provider_name: "YAML Import", model: "PyYAML", elapsed_ms: 0 },
        },
        { pushHistory: true, label: `YAML: ${data.graph?.title || file.name}` }
      );
      switchTab("visual");
      showToast(`Imported workflow from ${file.name}.`);
    } catch (err) {
      showToast(err.message, true);
    }
  }

  // ─── 13. Pan, Zoom, Tabs & Modals ──────────────────────────────────────────
  function applyTransform() {
    el.diagramViewport.style.transform = `translate(${state.panX}px, ${state.panY}px) scale(${state.zoom})`;
    el.zoomLabel.textContent = `${Math.round(state.zoom * 100)}%`;
  }

  function adjustZoom(delta) {
    if (!state.currentMermaid) return;
    state.zoom = Math.max(0.25, Math.min(3.5, Number((state.zoom + delta).toFixed(2))));
    applyTransform();
  }

  function resetZoom() {
    state.zoom = 1;
    state.panX = 0;
    state.panY = 0;
    applyTransform();
  }

  function fitZoom() {
    const svg = el.mermaidTarget.querySelector("svg");
    if (!svg) return;
    const cRect = el.viewVisual.getBoundingClientRect();
    const sRect = svg.getBoundingClientRect();
    if (!sRect.width || !sRect.height) return;
    const baseW = sRect.width / state.zoom;
    const baseH = sRect.height / state.zoom;
    state.zoom = Math.max(0.3, Math.min(1.5, (cRect.width * 0.86) / baseW, (cRect.height * 0.86) / baseH));
    state.panX = 0;
    state.panY = 0;
    applyTransform();
  }

  function switchTab(tabName) {
    state.activeTab = tabName;
    el.tabButtons.forEach((btn) => {
      const active = btn.dataset.tab === tabName;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-selected", String(active));
    });
    el.viewVisual.hidden = tabName !== "visual";
    el.viewEditor.hidden = tabName !== "editor";
    el.viewReport.hidden = tabName !== "report";
    el.viewData.hidden = tabName !== "data";
    el.viewDocs.hidden = tabName !== "docs";
  }

  function openDocsTab() {
    switchTab("docs");
    if (el.docsMainHeading) el.docsMainHeading.focus();
  }

  function syncDirectionRadios() {
    document.querySelectorAll('input[name="direction"]').forEach((r) => {
      r.checked = r.value === state.direction;
    });
  }

  function openAiModal(providerId = null) {
    const pid = providerId || state.currentProvider;
    el.modalProviderSelect.value = pid;
    refreshAiModalFields(pid);
    el.chkSessionPersist.checked = state.persistSession;
    el.chkNativeFallback.checked = state.allowNativeFallback;
    openTopLayer(el.modalAi);
  }

  function refreshAiModalFields(pid) {
    const spec = getProviderSpec(pid);
    if (!spec) return;
    el.modalApiKeyGroup.hidden = !spec.requires_api_key && spec.id !== "custom_openai";
    el.modalApiKey.value = state.apiKeys[pid] || "";
    el.modalApiKey.type = "password";
    el.btnToggleKey.textContent = "Show";

    el.modalBaseUrlGroup.hidden = !spec.allow_custom_url;
    el.modalBaseUrl.value = state.customUrls[pid] || spec.default_base_url || "";
  }

  async function openPromptModal() {
    if (!state.systemPromptText) {
      try {
        const resp = await fetch("/api/v1/prompt");
        if (resp.ok) {
          const data = await resp.json();
          state.systemPromptText = data.system_prompt_full || "";
        }
      } catch (_) {
        state.systemPromptText = "Could not load system prompt from backend.";
      }
    }
    el.promptContent.textContent = state.systemPromptText;
    openTopLayer(el.modalPrompt);
  }

  // ─── 14. Events & Global Keyboard Shortcuts ────────────────────────────────
  function bindEvents() {
    el.btnThemeToggle.addEventListener("click", cycleColorScheme);
    el.btnUndo.addEventListener("click", () => state.historyIndex > 0 && restoreSnapshot(state.historyIndex - 1));
    el.btnRedo.addEventListener("click", () => state.historyIndex < state.history.length - 1 && restoreSnapshot(state.historyIndex + 1));
    el.btnHistory.addEventListener("click", openHistoryModal);
    el.btnConfigAi.addEventListener("click", () => openAiModal());
    el.btnViewPrompt.addEventListener("click", openPromptModal);
    el.btnOpenDocs.addEventListener("click", openDocsTab);
    el.btnShortcuts.addEventListener("click", () => openTopLayer(el.modalShortcuts));

    el.btnEmptyFocus.addEventListener("click", () => el.processDescription.focus());
    el.btnEmptyDocs.addEventListener("click", openDocsTab);
    el.inputEmptyImportYaml.addEventListener("change", (e) => {
      handleImportYaml(e.target.files?.[0]);
      e.target.value = "";
    });

    document.querySelectorAll("[data-close-dialog]").forEach((btn) => {
      btn.addEventListener("click", () => closeTopLayer($(btn.dataset.closeDialog)));
    });

    el.processDescription.addEventListener("input", updateCharCount);
    el.btnClearText.addEventListener("click", () => {
      el.processDescription.value = "";
      updateCharCount();
      el.processDescription.focus();
    });

    el.providerSelect.addEventListener("change", (e) => selectProvider(e.target.value));
    el.modelSelect.addEventListener("change", (e) => {
      state.currentModel = e.target.value;
    });
    el.btnDiscoverModels.addEventListener("click", discoverLocalModels);

    document.querySelectorAll('input[name="direction"]').forEach((radio) => {
      radio.addEventListener("change", (e) => {
        state.direction = e.target.value;
        if (state.currentMermaid) {
          validateAndApplyMermaid(state.currentMermaid, {
            direction: state.direction,
            pushHistory: true,
            label: `Orientation ${state.direction}`,
          });
        }
      });
    });

    el.chkCriticalPath.addEventListener("change", (e) => {
      state.highlightCritical = e.target.checked;
      if (state.currentMermaid) {
        validateAndApplyMermaid(state.currentMermaid, {
          direction: state.direction,
          pushHistory: false,
        });
      }
    });

    el.btnGenerate.addEventListener("click", () => runGeneration());
    el.tabButtons.forEach((btn) => btn.addEventListener("click", () => switchTab(btn.dataset.tab)));

    el.btnRepairEditor.addEventListener("click", () =>
      validateAndApplyMermaid(el.mermaidCodeInput.value, { pushHistory: true, label: "Mermaid Repair" })
    );
    el.btnApplyEditor.addEventListener("click", () =>
      validateAndApplyMermaid(el.mermaidCodeInput.value, { pushHistory: true, label: "Mermaid Edit" })
    );

    // Pan & Zoom (only when a diagram is rendered)
    el.viewVisual.addEventListener(
      "wheel",
      (e) => {
        if (!state.currentMermaid) return;
        e.preventDefault();
        adjustZoom(e.deltaY < 0 ? 0.12 : -0.12);
      },
      { passive: false }
    );
    el.viewVisual.addEventListener("mousedown", (e) => {
      if (!state.currentMermaid || e.button !== 0) return;
      state.isDragging = true;
      state.dragStartX = e.clientX - state.panX;
      state.dragStartY = e.clientY - state.panY;
      el.viewVisual.classList.add("dragging");
    });
    window.addEventListener("mousemove", (e) => {
      if (!state.isDragging) return;
      state.panX = e.clientX - state.dragStartX;
      state.panY = e.clientY - state.dragStartY;
      applyTransform();
    });
    window.addEventListener("mouseup", () => {
      if (state.isDragging) {
        state.isDragging = false;
        el.viewVisual.classList.remove("dragging");
      }
    });

    el.btnZoomIn.addEventListener("click", () => adjustZoom(0.2));
    el.btnZoomOut.addEventListener("click", () => adjustZoom(-0.2));
    el.btnZoomReset.addEventListener("click", resetZoom);
    el.btnZoomFit.addEventListener("click", fitZoom);

    // Exports
    el.btnCopyMermaid.addEventListener("click", () => {
      navigator.clipboard
        .writeText(state.currentMermaid)
        .then(() => showToast("Mermaid code copied to clipboard."))
        .catch(() => showToast("Failed to copy to clipboard.", true));
    });
    el.btnExportSvg.addEventListener("click", exportAsSvg);
    el.btnExportPng.addEventListener("click", exportAsPng);
    el.btnExportPdf.addEventListener("click", exportAsPdf);
    el.btnExportYaml.addEventListener("click", () => exportStructured("yaml"));
    el.btnDownloadYaml2.addEventListener("click", () => exportStructured("yaml"));
    el.btnDownloadJson.addEventListener("click", () => exportStructured("json"));
    el.inputImportYaml.addEventListener("change", (e) => {
      handleImportYaml(e.target.files?.[0]);
      e.target.value = "";
    });

    el.btnFullscreen.addEventListener("click", () => {
      if (!document.fullscreenElement) {
        el.viewVisual.requestFullscreen().catch((err) => showToast(err.message, true));
      } else {
        document.exitFullscreen();
      }
    });

    // AI Modal
    el.modalProviderSelect.addEventListener("change", (e) => refreshAiModalFields(e.target.value));
    el.btnToggleKey.addEventListener("click", () => {
      const hidden = el.modalApiKey.type === "password";
      el.modalApiKey.type = hidden ? "text" : "password";
      el.btnToggleKey.textContent = hidden ? "Hide" : "Show";
    });
    el.btnSaveProviderCfg.addEventListener("click", () => {
      const pid = el.modalProviderSelect.value;
      const key = el.modalApiKey.value.trim();
      const baseUrl = el.modalBaseUrl.value.trim();
      if (key) state.apiKeys[pid] = key;
      else delete state.apiKeys[pid];
      if (baseUrl) state.customUrls[pid] = baseUrl;
      else delete state.customUrls[pid];
      state.persistSession = el.chkSessionPersist.checked;
      state.allowNativeFallback = el.chkNativeFallback.checked;
      syncSessionCredentials();
      updateCredentialStatus(getProviderSpec(state.currentProvider));
      closeTopLayer(el.modalAi);
      showToast("Provider configuration saved.");
    });
    el.btnClearProviderKey.addEventListener("click", () => {
      const pid = el.modalProviderSelect.value;
      delete state.apiKeys[pid];
      el.modalApiKey.value = "";
      syncSessionCredentials();
      updateCredentialStatus(getProviderSpec(state.currentProvider));
      showToast("API key cleared.");
    });

    el.btnCopyPrompt.addEventListener("click", () => {
      navigator.clipboard
        .writeText(state.systemPromptText)
        .then(() => showToast("System prompt copied."))
        .catch(() => showToast("Failed to copy.", true));
    });

    // Global Keyboard Shortcuts
    window.addEventListener("keydown", (e) => {
      const mod = e.ctrlKey || e.metaKey;
      const tag = document.activeElement?.tagName;
      const inInput = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";

      if (mod && e.key === "Enter") {
        e.preventDefault();
        runGeneration();
        return;
      }
      if (mod && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (state.activeTab === "editor") {
          validateAndApplyMermaid(el.mermaidCodeInput.value, { pushHistory: true, label: "Mermaid Edit (Ctrl+S)" });
        } else if (state.currentMermaid) {
          exportAsSvg();
        }
        return;
      }
      if (mod && !inInput && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey && state.historyIndex < state.history.length - 1) restoreSnapshot(state.historyIndex + 1);
        else if (!e.shiftKey && state.historyIndex > 0) restoreSnapshot(state.historyIndex - 1);
        return;
      }
      if (inInput) return;
      if (e.key === "+" || e.key === "=") adjustZoom(0.2);
      else if (e.key === "-") adjustZoom(-0.2);
      else if (e.key === "0") resetZoom();
      else if (e.key.toLowerCase() === "f") fitZoom();
      else if (e.key === "?") openTopLayer(el.modalShortcuts);
    });
  }

  function updateCharCount() {
    el.charCounter.textContent = `${el.processDescription.value.length.toLocaleString()} characters`;
  }

  function setBusy(busy, message = "") {
    el.btnGenerate.disabled = busy;
    el.btnGenerate.setAttribute("aria-busy", String(busy));
    el.btnGenerateLabel.textContent = busy ? "Processing…" : "Generate Architecture";
    if (busy && message) setStatus("working", message);
  }

  function setStatus(kind, message) {
    el.statusDot.className = "status-dot" + (kind === "working" ? " working" : kind === "error" ? " error" : "");
    el.statusText.textContent = message;
  }

  function showToast(message, isError = false) {
    const toast = h("div", { className: `toast${isError ? " toast--error" : ""}`, text: message });
    el.toastContainer.appendChild(toast);
    setTimeout(() => toast.remove(), 3400);
  }

  window.__ALVEA_SAFE_SET_HTML = safeSetHTML;
  document.addEventListener("DOMContentLoaded", init);
})();
