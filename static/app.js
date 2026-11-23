/**
 * ALVEA v3.1 — Process Architecture & Intelligence Studio
 * Vanilla JS client (English default, zero presets, CSP strict 'self', zero innerHTML XSS).
 */
(() => {
  "use strict";

  const CUSTOM_APIS_STORAGE_KEY = "alvea_custom_apis";

  // ─── 1. Application State ──────────────────────────────────────────────────
  const state = {
    providers: [],
    customApis: [],     // Non-secret custom API definitions in localStorage (keys remain in state.apiKeys RAM/session)
    editingCustomId: null,
    currentProvider: "native_python",
    currentModel: "alvea-bpa-v3",
    direction: "LR",
    highlightCritical: false,
    currentMermaid: "",
    currentGraph: null,
    currentAnalytics: null,
    currentReport: null,
    currentSop: null,
    currentMeta: null,
    activeTab: "visual",
    apiKeys: {},        // Browser RAM by default (optional sessionStorage) — NEVER localStorage
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
    coachTimer: null,
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
    apiKeyCount: $("api-key-count"),
    btnViewPrompt: $("btn-view-prompt"),
    btnOpenDocs: $("btn-open-docs"),
    btnShortcuts: $("btn-shortcuts"),
    btnThemeToggle: $("btn-theme-toggle"),
    themeLabel: $("theme-label"),

    processDescription: $("process-description"),
    charCounter: $("char-counter"),
    btnClearText: $("btn-clear-text"),
    btnPromptGuide: $("btn-prompt-guide"),
    coachActors: $("coach-actors"),
    coachDecisions: $("coach-decisions"),
    coachDurations: $("coach-durations"),
    coachOutcomes: $("coach-outcomes"),
    coachTip: $("coach-tip"),

    providerSelect: $("provider-select"),
    modelSelect: $("model-select"),
    btnDiscoverModels: $("btn-discover-models"),
    btnSidebarConfigApi: $("btn-sidebar-config-api"),
    btnSidebarAddCustom: $("btn-sidebar-add-custom"),
    providerBadges: $("provider-badges"),
    providerNote: $("provider-note"),
    providerKeyHint: $("provider-key-hint"),
    credentialStatus: $("credential-status"),
    chkCriticalPath: $("chk-critical-path"),
    btnGenerate: $("btn-generate"),
    btnGenerateLabel: $("btn-generate-label"),

    actorChipsContainer: $("actor-chips-container"),
    cognitiveDecisionsList: $("cognitive-decisions-list"),
    cognitiveRoutesText: $("cognitive-routes-text"),

    tabButtons: Array.from(document.querySelectorAll(".tab-btn[data-tab]")),
    viewVisual: $("view-visual"),
    viewEditor: $("view-editor"),
    viewReport: $("view-report"),
    viewSop: $("view-sop"),
    viewData: $("view-data"),
    viewDocs: $("view-docs"),
    docsMainHeading: $("docs-main-heading"),

    sopBarTitle: $("sop-bar-title"),
    sopContainer: $("sop-container"),
    btnCopySopMd: $("btn-copy-sop-md"),
    btnExportSopMd: $("btn-export-sop-md"),
    btnExportSopPdf: $("btn-export-sop-pdf"),

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
    aiTabBuiltin: $("ai-tab-builtin"),
    aiTabCustom: $("ai-tab-custom"),
    aiPanelBuiltin: $("ai-panel-builtin"),
    aiPanelCustom: $("ai-panel-custom"),
    modalAiFooterBuiltin: $("modal-ai-footer-builtin"),
    modalAiFooterCustom: $("modal-ai-footer-custom"),
    customApiCount: $("custom-api-count"),

    modalProviderSelect: $("modal-provider-select"),
    modalProviderHint: $("modal-provider-hint"),
    modalApiKeyGroup: $("modal-apikey-group"),
    modalApiKey: $("modal-api-key"),
    btnToggleKey: $("btn-toggle-key"),
    modalBaseUrlGroup: $("modal-baseurl-group"),
    modalBaseUrl: $("modal-base-url"),
    btnTestBuiltin: $("btn-test-builtin"),
    builtinTestResult: $("builtin-test-result"),
    chkSessionPersist: $("chk-session-persist"),
    chkNativeFallback: $("chk-native-fallback"),
    btnClearProviderKey: $("btn-clear-provider-key"),
    btnSaveProviderCfg: $("btn-save-provider-cfg"),

    customApiName: $("custom-api-name"),
    customApiProtocol: $("custom-api-protocol"),
    customApiUrl: $("custom-api-url"),
    customApiModels: $("custom-api-models"),
    customApiKey: $("custom-api-key"),
    btnToggleCustomKey: $("btn-toggle-custom-key"),
    customAuthHeader: $("custom-auth-header"),
    customAuthPrefix: $("custom-auth-prefix"),
    btnTestCustom: $("btn-test-custom"),
    btnSaveCustomApi: $("btn-save-custom-api"),
    btnCancelCustomEdit: $("btn-cancel-custom-edit"),
    customTestResult: $("custom-test-result"),
    customApiList: $("custom-api-list"),

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

  // ─── 6. Credentials (RAM / Optional sessionStorage) & Custom APIs ──────────
  function loadCustomApis() {
    try {
      const raw = JSON.parse(localStorage.getItem(CUSTOM_APIS_STORAGE_KEY) || "[]");
      if (!Array.isArray(raw)) {
        state.customApis = [];
        return;
      }
      state.customApis = raw
        .filter((c) => c && typeof c.id === "string" && typeof c.name === "string" && typeof c.base_url === "string")
        .map((c) => ({
          id: c.id,
          name: c.name.slice(0, 60),
          protocol: ["openai_compat", "gemini", "anthropic", "ollama"].includes(c.protocol) ? c.protocol : "openai_compat",
          base_url: c.base_url.slice(0, 256),
          models: Array.isArray(c.models) && c.models.length ? c.models.map(String) : ["custom-model"],
          auth_header: typeof c.auth_header === "string" ? c.auth_header.slice(0, 64) : "",
          auth_prefix: typeof c.auth_prefix === "string" ? c.auth_prefix : "__default__",
        }));
    } catch (_) {
      state.customApis = [];
    }
  }

  function saveCustomApisToStorage() {
    try {
      // Strictly non-secret metadata only; API keys are NEVER written to localStorage
      localStorage.setItem(CUSTOM_APIS_STORAGE_KEY, JSON.stringify(state.customApis));
    } catch (_) {
      /* Ignore storage quota errors */
    }
    updateApiCountBadge();
  }

  function updateApiCountBadge() {
    const keyCount = Object.values(state.apiKeys).filter(Boolean).length;
    const total = keyCount + state.customApis.length;
    if (el.apiKeyCount) {
      el.apiKeyCount.textContent = String(total);
      el.apiKeyCount.hidden = total === 0;
    }
    if (el.customApiCount) {
      el.customApiCount.textContent = String(state.customApis.length);
    }
  }

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
    updateApiCountBadge();
  }

  // ─── 7. Initialization (Clean Empty Canvas, Zero Presets) ──────────────────
  async function init() {
    applyColorScheme(getStoredScheme(), false);
    window.addEventListener("storage", (e) => {
      if (e.key === "alvea_color_scheme") applyColorScheme(getStoredScheme(), false);
    });

    [el.modalAi, el.modalPrompt, el.modalHistory, el.modalShortcuts].forEach(setupDialogEnhancements);
    loadCustomApis();
    loadSessionCredentials();
    updateApiCountBadge();
    initMermaid();
    bindEvents();
    setDiagramControlsEnabled(false);
    updatePromptCoach();

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
      el.btnCopySopMd,
      el.btnExportSopMd,
      el.btnExportSopPdf,
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

  function getCustomApiById(id) {
    return state.customApis.find((c) => c.id === id) || null;
  }

  function customApiToSpec(custom) {
    const protoLabels = {
      openai_compat: "OpenAI-Compatible",
      gemini: "Gemini Protocol",
      anthropic: "Anthropic Protocol",
      ollama: "Ollama Protocol",
    };
    return {
      id: custom.id,
      isCustom: true,
      name: custom.name,
      company: "Custom API",
      group: "custom",
      protocol: custom.protocol,
      default_base_url: custom.base_url,
      requires_api_key: false,
      supports_discovery: false,
      allow_custom_url: true,
      badges: ["Custom API", protoLabels[custom.protocol] || custom.protocol],
      privacy_note: `Custom endpoint: ${custom.base_url}`,
      key_hint: state.apiKeys[custom.id]
        ? "API key stored in browser memory for this custom endpoint."
        : "Optional: edit this custom API to attach or update an API key.",
      default_model: custom.models[0] || "custom-model",
      models: custom.models.map((m) => ({ id: m, label: m, badges: ["Custom"] })),
      customDef: custom,
    };
  }

  function getProviderSpec(id) {
    const custom = getCustomApiById(id);
    if (custom) return customApiToSpec(custom);
    return state.providers.find((p) => p.id === id) || null;
  }

  function populateProviderSelects() {
    const groups = [
      { key: "local", label: "Local · Zero API Key (Private)" },
      { key: "free_cloud", label: "Free Cloud Tiers (2026 Multi-Vendor)" },
      { key: "byok", label: "Other Providers / BYOK" },
    ];

    const buildMainSelect = (selectEl) => {
      const prev = selectEl.value;
      selectEl.replaceChildren();
      for (const grp of groups) {
        const items = state.providers.filter((p) => p.group === grp.key);
        if (!items.length) continue;
        const optgroup = h("optgroup", { label: grp.label });
        for (const p of items) {
          const keyMarker = p.requires_api_key ? (state.apiKeys[p.id] ? " [Key Ready]" : " [Set Key]") : "";
          optgroup.appendChild(h("option", { value: p.id, text: `${p.name} — ${p.company}${keyMarker}` }));
        }
        selectEl.appendChild(optgroup);
      }
      if (state.customApis.length > 0) {
        const customGrp = h("optgroup", { label: "Custom APIs (Added by You)" });
        for (const c of state.customApis) {
          const keyMarker = state.apiKeys[c.id] ? " [Key Ready]" : "";
          customGrp.appendChild(h("option", { value: c.id, text: `${c.name} (${c.protocol})${keyMarker}` }));
        }
        selectEl.appendChild(customGrp);
      }
      if (prev && Array.from(selectEl.options).some((o) => o.value === prev)) {
        selectEl.value = prev;
      }
    };

    const buildModalSelect = (selectEl) => {
      const prev = selectEl.value;
      selectEl.replaceChildren();
      for (const grp of groups) {
        const items = state.providers.filter((p) => p.group === grp.key && p.id !== "native_python");
        if (!items.length) continue;
        const optgroup = h("optgroup", { label: grp.label });
        for (const p of items) {
          const suffix = p.requires_api_key ? (state.apiKeys[p.id] ? " ✓ Key Set" : " · Key Required") : " · Local";
          optgroup.appendChild(h("option", { value: p.id, text: `${p.name}${suffix}` }));
        }
        selectEl.appendChild(optgroup);
      }
      if (prev && Array.from(selectEl.options).some((o) => o.value === prev)) {
        selectEl.value = prev;
      }
    };

    buildMainSelect(el.providerSelect);
    buildModalSelect(el.modalProviderSelect);
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
      else if (low.includes("free") || low.includes("custom")) cls = "badge badge--free";
      else if (low.includes("fast") || low.includes("lpu")) cls = "badge badge--fast";
      el.providerBadges.appendChild(h("span", { className: cls, text: b }));
    });

    el.providerNote.textContent = spec.privacy_note || "";
    if (el.providerKeyHint) {
      if (spec.key_hint && (spec.requires_api_key || spec.isCustom)) {
        el.providerKeyHint.textContent = spec.key_hint;
        el.providerKeyHint.hidden = false;
      } else {
        el.providerKeyHint.hidden = true;
      }
    }
    updateCredentialStatus(spec);
  }

  function updateCredentialStatus(spec) {
    if (!spec) return;
    if (spec.isCustom) {
      const hasKey = Boolean(state.apiKeys[spec.id]);
      el.credentialStatus.textContent = hasKey ? "Custom Key Ready · Edit" : "Custom API · Edit";
      el.credentialStatus.className = "credential-pill credential-pill--btn credential-pill--ok";
      return;
    }
    if (!spec.requires_api_key) {
      el.credentialStatus.textContent = spec.supports_discovery ? "Local · Configure URL" : "No key required";
      el.credentialStatus.className = "credential-pill credential-pill--btn credential-pill--ok";
      return;
    }
    const hasKey = Boolean(state.apiKeys[spec.id]);
    if (hasKey) {
      el.credentialStatus.textContent = "Key Ready · Edit";
      el.credentialStatus.className = "credential-pill credential-pill--btn credential-pill--ok";
    } else {
      const shortName = spec.name.split("(")[0].trim();
      el.credentialStatus.textContent = `Set ${shortName} Key →`;
      el.credentialStatus.className = "credential-pill credential-pill--btn credential-pill--warn";
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

      const isCustom = Boolean(spec && spec.isCustom && spec.customDef);
      const customDef = isCustom ? spec.customDef : null;

      const payload = {
        text,
        provider: isCustom ? "custom_openai" : providerId,
        model: modelId,
        direction: state.direction,
        highlight_critical: state.highlightCritical,
        base_url: isCustom ? customDef.base_url : state.customUrls[providerId] || null,
        allow_native_fallback: state.allowNativeFallback,
      };
      if (isCustom) {
        payload.custom_protocol = customDef.protocol;
        if (customDef.auth_header) payload.custom_auth_header = customDef.auth_header;
        if (customDef.auth_prefix !== "__default__") payload.custom_auth_prefix = customDef.auth_prefix;
      }

      const resp = await fetch("/api/v1/generate", {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
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
    state.currentSop = data.sop || null;
    state.currentMeta = data.meta || null;

    setDiagramControlsEnabled(Boolean(state.currentMermaid));
    el.mermaidCodeInput.value = state.currentMermaid;
    renderValidationBanner(data.validation);
    renderMetricsStrip(state.currentAnalytics);
    renderCognitivePanel(state.currentReport?.cognitive);
    renderExecutiveReport(state.currentReport, state.currentAnalytics);
    renderSopDocument(state.currentSop);
    renderDataPreview();

    await renderMermaidSvg(state.currentMermaid);

    if (pushHistory) pushSnapshot(label);

    const meta = state.currentMeta || {};
    el.telemetryText.textContent = `${meta.provider_name || "ALVEA"} · ${meta.model || ""} · ${meta.elapsed_ms ?? 0} ms · graph ${state.direction}`;
    setStatus("ok", "Architecture, Executive Report & SOP rendered.");
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

  function renderSopDocument(sop) {
    if (!sop || !Array.isArray(sop.steps) || !sop.steps.length) {
      el.sopBarTitle.textContent = "Standard Operating Procedure (ISO-Style Operational Runbook)";
      el.sopContainer.replaceChildren(
        h("p", {
          className: "dialog-intro",
          text: "No Standard Operating Procedure generated yet. Generate a workflow architecture (or import YAML) to automatically compile a numbered, role-assigned SOP ready for PDF and Markdown export.",
        })
      );
      return;
    }

    el.sopBarTitle.textContent = `${sop.sop_id} · Rev ${sop.version || "1.0"} · ${sop.steps.length} Operational Steps`;

    const roleRows = (sop.roles_and_responsibilities || []).map((r) =>
      h(
        "tr",
        {},
        h("td", {}, h("strong", { text: r.role_name })),
        h("td", { text: r.role_kind }),
        h("td", { className: "tabular-nums", text: (r.step_numbers || []).join(", ") || "—" }),
        h("td", { className: "tabular-nums", text: `${r.automated_steps}/${r.step_count}` }),
        h("td", { text: r.responsibility_summary })
      )
    );

    const modeBadgeClass = (mode) => {
      if (mode === "Automated") return "sop-mode-badge sop-mode-badge--auto";
      if (mode === "Decision Gateway" || mode === "Wait / SLA") return "sop-mode-badge sop-mode-badge--decision";
      if (mode === "Milestone") return "sop-mode-badge sop-mode-badge--milestone";
      return "sop-mode-badge";
    };

    const stepRows = sop.steps.map((st) => {
      const routeChips = [];
      (st.next_steps || []).forEach((nxt) => {
        routeChips.push(
          h("span", {
            className: "sop-route-chip",
            text: `${nxt.condition} → Step ${nxt.target_step}`,
          })
        );
      });
      (st.rework_loops || []).forEach((lp) => {
        routeChips.push(
          h("span", {
            className: "sop-route-chip sop-route-chip--loop",
            text: `↩ ${lp.condition} → Return to Step ${lp.target_step}`,
          })
        );
      });

      const stepLabel = st.is_critical_path ? `${st.step_number} ★` : st.step_number;
      return h(
        "tr",
        {},
        h("td", {
          className: `sop-step-num${st.is_critical_path ? " sop-step-num--cp" : ""}`,
          title: st.is_critical_path ? "On NetworkX Critical Path" : "",
          text: stepLabel,
        }),
        h("td", { text: st.owner }),
        h("td", {}, h("span", { className: modeBadgeClass(st.execution_mode), text: st.execution_mode })),
        h(
          "td",
          {},
          h("div", { text: st.instruction }),
          routeChips.length ? h("div", { className: "sop-route-list" }, ...routeChips) : null
        ),
        h("td", { className: "tabular-nums", text: st.sla_display || "—" })
      );
    });

    const nodes = [
      h(
        "div",
        { className: "report-header" },
        h(
          "div",
          {},
          h("h2", { className: "report-title", text: sop.title }),
          h("p", {
            className: "provider-note",
            text: `Auto-generated from canonical ProcessGraph · Topologically ordered with parallel track & loop cross-references`,
          })
        ),
        h("div", { className: "report-grade-badge tabular-nums", text: sop.sop_id })
      ),
      h(
        "div",
        { className: "sop-meta-grid" },
        h("div", { className: "sop-meta-cell" }, h("span", { className: "kpi-label", text: "Document ID" }), h("strong", { text: sop.sop_id })),
        h("div", { className: "sop-meta-cell" }, h("span", { className: "kpi-label", text: "Version" }), h("strong", { text: `Rev ${sop.version || "1.0"}` })),
        h("div", { className: "sop-meta-cell" }, h("span", { className: "kpi-label", text: "Effective Date" }), h("strong", { text: sop.effective_date || "—" })),
        h("div", { className: "sop-meta-cell" }, h("span", { className: "kpi-label", text: "Est. Cycle Time" }), h("strong", { text: sop.estimated_cycle_time || "—" }))
      ),
      h(
        "section",
        { className: "report-section" },
        h("h3", { text: "1. Purpose & Scope" }),
        h("p", {}, h("strong", { text: "Purpose: " }), sop.purpose),
        h("p", {}, h("strong", { text: "Scope: " }), sop.scope)
      ),
      h(
        "section",
        { className: "report-section" },
        h("h3", { text: "2. Roles & Responsibilities" }),
        h(
          "table",
          { className: "report-table" },
          h(
            "thead",
            {},
            h(
              "tr",
              {},
              h("th", { text: "Role / System" }),
              h("th", { text: "Type" }),
              h("th", { text: "Assigned Steps" }),
              h("th", { text: "Auto" }),
              h("th", { text: "Primary Responsibilities" })
            )
          ),
          h("tbody", {}, ...roleRows)
        )
      ),
      h(
        "section",
        { className: "report-section" },
        h("h3", { text: "3. Step-by-Step Operating Procedure" }),
        h(
          "table",
          { className: "report-table" },
          h(
            "thead",
            {},
            h(
              "tr",
              {},
              h("th", { text: "Step" }),
              h("th", { text: "Owner" }),
              h("th", { text: "Mode" }),
              h("th", { text: "Procedure & Routing" }),
              h("th", { text: "SLA" })
            )
          ),
          h("tbody", {}, ...stepRows)
        ),
        h("p", { className: "hint-text", text: "★ Denotes a step on the NetworkX Critical Path." })
      ),
    ];

    if (Array.isArray(sop.decision_rules) && sop.decision_rules.length > 0) {
      nodes.push(
        h(
          "section",
          { className: "report-section" },
          h("h3", { text: "4. Decision & Routing Matrix" }),
          h(
            "table",
            { className: "report-table" },
            h(
              "thead",
              {},
              h(
                "tr",
                {},
                h("th", { text: "Step" }),
                h("th", { text: "Decision Gateway" }),
                h("th", { text: "Owner" }),
                h("th", { text: "Routing Rules" })
              )
            ),
            h(
              "tbody",
              {},
              ...sop.decision_rules.map((rule) =>
                h(
                  "tr",
                  {},
                  h("td", { className: "sop-step-num", text: String(rule.step_number || "?") }),
                  h("td", { text: String(rule.gateway || "") }),
                  h("td", { text: String(rule.owner || "") }),
                  h(
                    "td",
                    {
                      text: (rule.branches || [])
                        .map((b) => `${b.condition} → ${b.action}`)
                        .join("  |  "),
                    }
                  )
                )
              )
            )
          )
        )
      );
    }

    const secBase = sop.decision_rules?.length ? 5 : 4;
    nodes.push(
      h(
        "section",
        { className: "report-section" },
        h("h3", { text: `${secBase}. Exception Handling & Rework Loops` }),
        h(
          "ul",
          { className: "report-list" },
          ...(sop.rework_and_exceptions || []).map((item) => h("li", { className: "report-card-item", text: item }))
        )
      ),
      h(
        "section",
        { className: "report-section" },
        h("h3", { text: `${secBase + 1}. SLA & Quality Controls` }),
        h(
          "ul",
          { className: "report-list" },
          ...(sop.sla_and_controls || []).map((ctrl) => h("li", { className: "report-card-item", text: ctrl }))
        )
      )
    );

    el.sopContainer.replaceChildren(...nodes);
  }

  function renderDataPreview() {
    if (!state.currentGraph) {
      el.dataPreview.textContent = "// Canonical ProcessGraph and NetworkX metrics will appear here after generation.";
      return;
    }
    el.dataPreview.textContent = JSON.stringify(
      {
        schema_version: "3.1",
        process_graph: state.currentGraph,
        analytics: state.currentAnalytics,
        sop_id: state.currentSop?.sop_id || null,
      },
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
      sop: state.currentSop,
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
    updatePromptCoach();
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

  async function captureDiagramPngBase64() {
    const svg = el.mermaidTarget.querySelector("svg");
    if (!svg) return null;
    try {
      const blob = await renderSvgToPngBlob(svg, 2);
      if (blob.size >= 1_600_000) return null;
      return await new Promise((res) => {
        const reader = new FileReader();
        reader.onloadend = () => res(reader.result);
        reader.readAsDataURL(blob);
      });
    } catch (_) {
      return null;
    }
  }

  async function exportSop(format) {
    if (!state.currentMermaid) return showToast("Generate a workflow before exporting the SOP.", true);
    const isPdf = format === "pdf";
    setBusy(true, isPdf ? "Generating SOP PDF Document with ReportLab…" : "Compiling SOP Markdown…");
    try {
      const pngBase64 = isPdf ? await captureDiagramPngBase64() : null;
      const endpoint = isPdf ? "/api/v1/export/sop/pdf" : "/api/v1/export/sop/markdown";
      const resp = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: state.currentGraph?.title || "Workflow Process",
          mermaid: state.currentMermaid,
          direction: state.direction,
          diagram_png_base64: pngBase64,
        }),
      });
      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.error || `SOP export failed (${resp.status})`);
      }
      const sopSlug = (state.currentSop?.sop_id || "alvea_sop").toLowerCase();
      downloadBlob(await resp.blob(), isPdf ? `${sopSlug}_document.pdf` : `${sopSlug}_document.md`);
      showToast(isPdf ? "SOP PDF downloaded." : "SOP Markdown (.md) downloaded.");
    } catch (err) {
      showToast(err.message, true);
    } finally {
      setBusy(false);
    }
  }

  async function copySopMarkdown() {
    if (!state.currentMermaid) return showToast("Generate a workflow first.", true);
    try {
      const resp = await fetch("/api/v1/export/sop/markdown", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: state.currentGraph?.title || "Workflow Process",
          mermaid: state.currentMermaid,
          direction: state.direction,
        }),
      });
      if (!resp.ok) throw new Error("Failed to render SOP Markdown.");
      const mdText = await resp.text();
      await navigator.clipboard.writeText(mdText);
      showToast("SOP Markdown copied to clipboard.");
    } catch (err) {
      showToast(err.message || "Failed to copy SOP Markdown.", true);
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
    el.viewSop.hidden = tabName !== "sop";
    el.viewData.hidden = tabName !== "data";
    el.viewDocs.hidden = tabName !== "docs";
  }

  function openDocsTab(sectionId = null) {
    switchTab("docs");
    if (sectionId) {
      const target = document.getElementById(sectionId);
      if (target) {
        requestAnimationFrame(() => target.scrollIntoView({ behavior: "smooth", block: "start" }));
        return;
      }
    }
    if (el.docsMainHeading) el.docsMainHeading.focus();
  }

  function syncDirectionRadios() {
    document.querySelectorAll('input[name="direction"]').forEach((r) => {
      r.checked = r.value === state.direction;
    });
  }

  // ─── Live Prompting Design Coach (100% Client-Side) ────────────────────────
  function updatePromptCoach() {
    const raw = (el.processDescription?.value || "").trim();
    const hasActors =
      /(?:^|\n)\s*[-*\d.)\s]*[A-Za-z][A-Za-z0-9 &/._-]{1,32}\s*(?:->|:)\s*\S+/m.test(raw) ||
      /\b(?:customer|client|user|manager|finance|legal|hr|it|system|api|erp|crm|portal|team|support|analyst|director|vendor|cliente|usuario|gerente|finanzas|sistema|equipo)\b/i.test(raw);
    const hasDecisions =
      /\b(?:if|else\s+if|otherwise|when|whether|approved|rejected|valid|invalid|si|sino|en caso contrario|aprobado|rechazado)\b/i.test(raw);
    const hasDurations =
      /\b\d+(?:[.,]\d+)?\s*(?:min(?:ute)?s?|m|hrs?|hours?|h|days?|d|weeks?|w|sec(?:ond)?s?|s|horas?|d[ií]as?)\b/i.test(raw);
    const hasOutcomes =
      /\b(?:complete[ds]?|finish(?:ed)?|close[ds]?|fulfilled|approved|rejected|denied|cancel(?:led|ed)?|archived|delivered|published|deployed|finaliz|completad|cerrad|rechazad|aprobad|entregad)\b/i.test(raw);

    el.coachActors?.classList.toggle("coach-pill--met", hasActors);
    el.coachDecisions?.classList.toggle("coach-pill--met", hasDecisions);
    el.coachDurations?.classList.toggle("coach-pill--met", hasDurations);
    el.coachOutcomes?.classList.toggle("coach-pill--met", hasOutcomes);

    if (!el.coachTip) return;
    if (!raw) {
      el.coachTip.textContent =
        'Tip: Prefix steps with roles like "Finance: Review invoice [30m]" to generate clean swimlanes and SOP ownership.';
    } else if (!hasActors) {
      el.coachTip.textContent =
        'Tip: Name explicit actors (e.g. "Requester: Submit form" or "API -> ERP: Sync record") so ALVEA creates clean swimlanes.';
    } else if (!hasDecisions) {
      el.coachTip.textContent =
        'Tip: Add conditional branches ("If approved, ... Otherwise, ...") to model decision gateways and routing rules.';
    } else if (!hasDurations) {
      el.coachTip.textContent =
        'Tip: Include step durations like [15m] or [2h] so NetworkX calculates real cycle time in minutes and SOP SLAs.';
    } else if (!hasOutcomes) {
      el.coachTip.textContent =
        'Tip: State clear terminal outcomes (e.g. "Order Fulfilled" or "Request Rejected") to avoid dead-end anomalies.';
    } else {
      el.coachTip.textContent =
        "Strong workflow prompt! Actors, branches, durations, and outcomes detected — ready for Diagram, Audit & SOP.";
    }
  }

  function schedulePromptCoach() {
    if (state.coachTimer) clearTimeout(state.coachTimer);
    state.coachTimer = setTimeout(updatePromptCoach, 180);
  }

  // ─── API Keys & Custom API Manager Modal ───────────────────────────────────
  function switchAiModalTab(mode) {
    const isCustom = mode === "custom";
    el.aiTabBuiltin.classList.toggle("active", !isCustom);
    el.aiTabBuiltin.setAttribute("aria-selected", String(!isCustom));
    el.aiTabCustom.classList.toggle("active", isCustom);
    el.aiTabCustom.setAttribute("aria-selected", String(isCustom));
    el.aiPanelBuiltin.hidden = isCustom;
    el.aiPanelCustom.hidden = !isCustom;
    el.modalAiFooterBuiltin.hidden = isCustom;
    el.modalAiFooterCustom.hidden = !isCustom;
    if (isCustom) renderCustomApiList();
  }

  function openAiModal(providerId = null, mode = "builtin") {
    const targetId = providerId || state.currentProvider;
    const custom = getCustomApiById(targetId);

    el.chkSessionPersist.checked = state.persistSession;
    el.chkNativeFallback.checked = state.allowNativeFallback;
    el.builtinTestResult.textContent = "";
    el.builtinTestResult.className = "test-result";
    el.customTestResult.textContent = "";
    el.customTestResult.className = "test-result";

    if (mode === "custom" || custom) {
      switchAiModalTab("custom");
      if (custom) loadCustomIntoForm(custom);
      else resetCustomForm();
    } else {
      switchAiModalTab("builtin");
      const fallbackId = targetId === "native_python" ? "gemini" : targetId;
      if (Array.from(el.modalProviderSelect.options).some((o) => o.value === fallbackId)) {
        el.modalProviderSelect.value = fallbackId;
      }
      refreshAiModalFields(el.modalProviderSelect.value);
    }

    openTopLayer(el.modalAi);
    if (mode !== "custom" && !custom && !el.modalApiKeyGroup.hidden) {
      requestAnimationFrame(() => el.modalApiKey.focus());
    }
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

    if (el.modalProviderHint) {
      el.modalProviderHint.textContent = spec.key_hint || spec.privacy_note || "";
    }
    el.builtinTestResult.textContent = "";
    el.builtinTestResult.className = "test-result";
  }

  async function runConnectionTest({
    provider,
    model,
    apiKey,
    baseUrl,
    customProtocol = null,
    customAuthHeader = null,
    customAuthPrefix = null,
    resultEl,
    buttonEl,
  }) {
    buttonEl.disabled = true;
    const origLabel = buttonEl.textContent;
    buttonEl.textContent = "Testing…";
    resultEl.textContent = "Probing endpoint…";
    resultEl.className = "test-result";
    try {
      const headers = { "Content-Type": "application/json" };
      if (apiKey) headers["X-API-Key"] = apiKey;
      const body = {
        provider,
        model: model || null,
        base_url: baseUrl || null,
      };
      if (customProtocol) body.custom_protocol = customProtocol;
      if (customAuthHeader) body.custom_auth_header = customAuthHeader;
      if (customAuthPrefix !== null && customAuthPrefix !== "__default__") {
        body.custom_auth_prefix = customAuthPrefix;
      }

      const resp = await fetch("/api/v1/providers/test", {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        resultEl.textContent = `✗ ${data.message || data.error || `HTTP ${resp.status}`}`;
        resultEl.className = "test-result test-result--err";
        return;
      }
      resultEl.textContent = `✓ ${data.message || "Connected."}`;
      resultEl.className = "test-result test-result--ok";
    } catch (_) {
      resultEl.textContent = "✗ Connection test failed (network/server error).";
      resultEl.className = "test-result test-result--err";
    } finally {
      buttonEl.disabled = false;
      buttonEl.textContent = origLabel;
    }
  }

  function resetCustomForm() {
    state.editingCustomId = null;
    el.customApiName.value = "";
    el.customApiProtocol.value = "openai_compat";
    el.customApiUrl.value = "";
    el.customApiModels.value = "";
    el.customApiKey.value = "";
    el.customApiKey.type = "password";
    el.btnToggleCustomKey.textContent = "Show";
    el.customAuthHeader.value = "";
    el.customAuthPrefix.value = "__default__";
    el.btnSaveCustomApi.textContent = "Add Custom API";
    el.btnCancelCustomEdit.hidden = true;
    el.customTestResult.textContent = "";
    el.customTestResult.className = "test-result";
  }

  function loadCustomIntoForm(custom) {
    state.editingCustomId = custom.id;
    el.customApiName.value = custom.name;
    el.customApiProtocol.value = custom.protocol;
    el.customApiUrl.value = custom.base_url;
    el.customApiModels.value = (custom.models || []).join(", ");
    el.customApiKey.value = state.apiKeys[custom.id] || "";
    el.customApiKey.type = "password";
    el.btnToggleCustomKey.textContent = "Show";
    el.customAuthHeader.value = custom.auth_header || "";
    el.customAuthPrefix.value = custom.auth_prefix || "__default__";
    el.btnSaveCustomApi.textContent = "Update Custom API";
    el.btnCancelCustomEdit.hidden = false;
    el.customTestResult.textContent = "";
    el.customTestResult.className = "test-result";
  }

  function readCustomFormValues() {
    const name = el.customApiName.value.trim();
    const protocol = el.customApiProtocol.value;
    const base_url = el.customApiUrl.value.trim();
    const models = el.customApiModels.value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const api_key = el.customApiKey.value.trim();
    const auth_header = el.customAuthHeader.value.trim();
    const auth_prefix = el.customAuthPrefix.value;
    return { name, protocol, base_url, models, api_key, auth_header, auth_prefix };
  }

  function saveCustomApi() {
    const v = readCustomFormValues();
    if (!v.name) return showToast("Please provide a Display Name for your Custom API.", true);
    if (!v.base_url || !/^https?:\/\//i.test(v.base_url)) {
      return showToast("Please provide a valid http:// (localhost) or https:// Base URL.", true);
    }
    if (!v.models.length) return showToast("Please provide at least one Model ID.", true);

    const id = state.editingCustomId || `custom_api_${Date.now().toString(36)}`;
    const record = {
      id,
      name: v.name.slice(0, 60),
      protocol: v.protocol,
      base_url: v.base_url.slice(0, 256),
      models: v.models,
      auth_header: v.auth_header.slice(0, 64),
      auth_prefix: v.auth_prefix,
    };

    const existingIdx = state.customApis.findIndex((c) => c.id === id);
    if (existingIdx >= 0) state.customApis[existingIdx] = record;
    else state.customApis.push(record);

    if (v.api_key) state.apiKeys[id] = v.api_key;
    else delete state.apiKeys[id];

    saveCustomApisToStorage();
    syncSessionCredentials();
    populateProviderSelects();
    selectProvider(id);
    renderCustomApiList();
    resetCustomForm();
    showToast(`Custom API '${record.name}' saved and selected.`);
  }

  function deleteCustomApi(id) {
    state.customApis = state.customApis.filter((c) => c.id !== id);
    delete state.apiKeys[id];
    if (state.editingCustomId === id) resetCustomForm();
    saveCustomApisToStorage();
    syncSessionCredentials();
    populateProviderSelects();
    if (state.currentProvider === id) selectProvider("native_python");
    renderCustomApiList();
    showToast("Custom API removed.");
  }

  function renderCustomApiList() {
    el.customApiList.replaceChildren();
    if (!state.customApis.length) {
      el.customApiList.appendChild(
        h("p", {
          className: "hint-text",
          text: "No custom APIs added yet. Fill in the form above to add DeepSeek, Together, LiteLLM, vLLM, or any OpenAI / Gemini / Anthropic / Ollama gateway.",
        })
      );
      return;
    }

    state.customApis.forEach((c) => {
      const hasKey = Boolean(state.apiKeys[c.id]);
      el.customApiList.appendChild(
        h(
          "div",
          { className: "history-row" },
          h(
            "div",
            {},
            h("strong", { text: `${c.name}${hasKey ? " (Key in RAM)" : ""}` }),
            h("div", {
              className: "hint-text",
              text: `${c.protocol} · ${c.base_url} · Models: ${c.models.join(", ")}`,
            })
          ),
          h(
            "div",
            { className: "btn-group" },
            h("button", {
              className: "btn btn-outline btn-xs",
              type: "button",
              text: "Use",
              onClick: () => {
                selectProvider(c.id);
                closeTopLayer(el.modalAi);
                showToast(`Switched provider to ${c.name}.`);
              },
            }),
            h("button", {
              className: "btn btn-outline btn-xs",
              type: "button",
              text: "Edit",
              onClick: () => loadCustomIntoForm(c),
            }),
            h("button", {
              className: "btn btn-ghost btn-xs",
              type: "button",
              text: "Delete",
              onClick: () => deleteCustomApi(c.id),
            })
          )
        )
      );
    });
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
    el.btnOpenDocs.addEventListener("click", () => openDocsTab());
    el.btnShortcuts.addEventListener("click", () => openTopLayer(el.modalShortcuts));

    el.btnEmptyFocus.addEventListener("click", () => el.processDescription.focus());
    el.btnEmptyDocs.addEventListener("click", () => openDocsTab());
    el.btnPromptGuide.addEventListener("click", () => openDocsTab("doc-prompting"));
    el.inputEmptyImportYaml.addEventListener("change", (e) => {
      handleImportYaml(e.target.files?.[0]);
      e.target.value = "";
    });

    document.querySelectorAll("[data-close-dialog]").forEach((btn) => {
      btn.addEventListener("click", () => closeTopLayer($(btn.dataset.closeDialog)));
    });

    el.processDescription.addEventListener("input", () => {
      updateCharCount();
      schedulePromptCoach();
    });
    el.btnClearText.addEventListener("click", () => {
      el.processDescription.value = "";
      updateCharCount();
      updatePromptCoach();
      el.processDescription.focus();
    });

    el.providerSelect.addEventListener("change", (e) => selectProvider(e.target.value));
    el.modelSelect.addEventListener("change", (e) => {
      state.currentModel = e.target.value;
    });
    el.btnDiscoverModels.addEventListener("click", discoverLocalModels);
    el.credentialStatus.addEventListener("click", () => openAiModal(state.currentProvider));
    el.btnSidebarConfigApi.addEventListener("click", () => openAiModal(state.currentProvider, "builtin"));
    el.btnSidebarAddCustom.addEventListener("click", () => openAiModal(null, "custom"));

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
    el.btnCopySopMd.addEventListener("click", copySopMarkdown);
    el.btnExportSopMd.addEventListener("click", () => exportSop("markdown"));
    el.btnExportSopPdf.addEventListener("click", () => exportSop("pdf"));
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

    // AI & Custom API Manager Modal
    el.aiTabBuiltin.addEventListener("click", () => switchAiModalTab("builtin"));
    el.aiTabCustom.addEventListener("click", () => switchAiModalTab("custom"));
    el.modalProviderSelect.addEventListener("change", (e) => refreshAiModalFields(e.target.value));
    el.btnToggleKey.addEventListener("click", () => {
      const hidden = el.modalApiKey.type === "password";
      el.modalApiKey.type = hidden ? "text" : "password";
      el.btnToggleKey.textContent = hidden ? "Hide" : "Show";
    });
    el.btnToggleCustomKey.addEventListener("click", () => {
      const hidden = el.customApiKey.type === "password";
      el.customApiKey.type = hidden ? "text" : "password";
      el.btnToggleCustomKey.textContent = hidden ? "Hide" : "Show";
    });
    el.btnTestBuiltin.addEventListener("click", () => {
      const pid = el.modalProviderSelect.value;
      const spec = getProviderSpec(pid);
      runConnectionTest({
        provider: pid,
        model: spec?.default_model || null,
        apiKey: el.modalApiKey.value.trim(),
        baseUrl: el.modalBaseUrl.value.trim() || null,
        resultEl: el.builtinTestResult,
        buttonEl: el.btnTestBuiltin,
      });
    });
    el.btnTestCustom.addEventListener("click", () => {
      const v = readCustomFormValues();
      if (!v.base_url) {
        el.customTestResult.textContent = "✗ Enter a Base URL first.";
        el.customTestResult.className = "test-result test-result--err";
        return;
      }
      runConnectionTest({
        provider: "custom_openai",
        model: v.models[0] || "custom-model",
        apiKey: v.api_key,
        baseUrl: v.base_url,
        customProtocol: v.protocol,
        customAuthHeader: v.auth_header || null,
        customAuthPrefix: v.auth_prefix,
        resultEl: el.customTestResult,
        buttonEl: el.btnTestCustom,
      });
    });
    el.btnSaveCustomApi.addEventListener("click", saveCustomApi);
    el.btnCancelCustomEdit.addEventListener("click", resetCustomForm);

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
      populateProviderSelects();
      selectProvider(pid);
      closeTopLayer(el.modalAi);
      showToast("Provider configuration saved and active.");
    });
    el.btnClearProviderKey.addEventListener("click", () => {
      const pid = el.modalProviderSelect.value;
      delete state.apiKeys[pid];
      el.modalApiKey.value = "";
      syncSessionCredentials();
      populateProviderSelects();
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
