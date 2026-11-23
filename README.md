# ALVEA — Process Architecture & Intelligence Studio

> *"From operational narrative to executive architecture."*

**ALVEA v3.0** is a clean, offline-first web studio backed by **Python**, **NetworkX** graph theory, **ReportLab** executive PDF generation, and a hybrid **Local / Multi-LLM** workflow engine. It converts free-form or structured process descriptions into executive **Mermaid.js Swimlane diagrams**, real-time structural diagnostics, and exportable architecture deliverables — with a built-in user guide directly inside the application.

---

## Core Capabilities

### 1. Next-Generation Workflow Engine (v3.0)
* **Native Python Deterministic Engine (`native_python`, 100% Offline / Zero API):** Industry-agnostic English & Spanish workflow parser supporting:
  * Free prose, numbered/bulleted lists, `Actor: Action` scripts, and `Source -> Target: Action` handoff chains.
  * **Parallel Fork/Join blocks** (`In parallel:`, `Simultaneously`, `Meanwhile`) with automatic synchronization (`Sync / Join`).
  * **Multi-branch decision gateways** (`If / Else if / Otherwise`) and **rework loops** (`Returns to`, `Rework`, `Fix and resubmit`).
  * **9 semantic BPMN-inspired node types:** `start`, `task`, `system` (cylinder), `subprocess`, `wait` (SLA/timer flag), `decision` (diamond), `parallel` (hexagon), `end_success`, and `end_reject`.
  * **Explicit SLA / duration parsing** (`15m`, `2h`, `3d`) feeding weighted NetworkX critical path analysis.
* **Local LLMs (Zero Cloud API):**
  * **Ollama Local** (`http://127.0.0.1:11434`) with live `/api/tags` auto-discovery (`qwen3.8:27b`, `qwen3-coder:30b`, `gemma4:12b`, `gemma4:e4b`, `llama3.3:70b`, `llama3.1:8b`, `llama3.2:3b`, `deepseek-r1:8b`).
  * **LM Studio / Local OpenAI-Compatible** (`http://127.0.0.1:1234/v1`) with `/v1/models` auto-discovery.
* **Free-Tier Cloud Providers (2026 Multi-Vendor):**
  * **Google Gemini** (`gemini-3.8-flash`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`, `gemini-2.5-flash`).
  * **Groq Cloud** (`llama-3.3-70b-versatile`, `qwen/qwen3.8-27b`, `openai/gpt-oss-120b`, `llama-3.1-8b-instant`).
  * **OpenRouter (`:free`)** (`openrouter/free`, `google/gemma-4-31b-it:free`, `google/gemma-4-26b-a4b-it:free`, `qwen/qwen3.8-27b:free`, `nvidia/nemotron-3.5-lightning:free`, `nvidia/nemotron-3-ultra-550b-a55b:free`).
  * **Cerebras Inference** (`qwen-3.8-27b`, `gpt-oss-120b`) and **GitHub Models**.
* **BYOK Optional:** Mistral AI, OpenAI (`gpt-4.1`, `o4-mini`), Anthropic Claude (`tool_use`), and custom OpenAI-compatible endpoints.
* **5-Level Self-Repair Pipeline:** Strict JSON Schema -> automatic mode downgrade -> `<think>` stripping & local JSON repair -> single LLM self-repair -> Mermaid-to-Graph fallback -> optional offline Python fallback.

### 2. Live NetworkX Graph Intelligence
Every workflow — generated locally, via LLM, edited manually in Mermaid, or imported from YAML — is audited in real time:
* **Weighted Critical Path** over condensed DAG (measured in minutes when explicit SLAs exist, or relative complexity points).
* **Bottleneck Ranking** via betweenness centrality, incident handoff pressure, manual workload, and wait states.
* **McCabe Cyclomatic Complexity**, automation coverage, cross-lane handoff ratio, rework cycles, structural anomalies, and operational Efficiency Grade (`A+` to `C`).

### 3. Clean Editorial Studio & Built-In Documentation
* Clean blank-canvas workspace (no hardcoded sample business maps).
* **Integrated User Guide (`Docs` tab / `Guide` header button)** covering syntax patterns, engines, NetworkX metrics, shortcuts, exports, and security — 100% available offline inside the app.
* System / Light / Dark themes (`color-scheme: light dark` + `light-dark()`), Undo/Redo session history (30 versions), Horizontal (`LR`) / Vertical (`TD`) orientation toggle, Critical Path highlight, and exports to **PNG HD (3x)**, **SVG**, **Executive PDF (ReportLab)**, **YAML**, and **JSON**.

---

## Quick Start

### One-Click Launch (Windows)
Double-click **`start_alvea.bat`**. It automatically detects Python 3.11+ (or `.venv`), installs dependencies from `requirements.txt` if missing, binds the first available port starting at `8000`, and opens ALVEA in your default browser.

### Manual Launch (Windows / macOS / Linux)
```bash
# 1. Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start ALVEA and open browser automatically
python run_alvea.py --open
```

CLI options:
```bash
python run_alvea.py --host 127.0.0.1 --port 8080 --open
python run_alvea.py --check
```

### Run Test Suite
```bash
python -m unittest discover -s tests -v
```

---

## Security & Privacy by Design

* **Zero Server-Side Key Persistence:** API keys stay in browser RAM by default (optional `sessionStorage`), travel only via HTTP headers (`X-API-Key` / `x-goog-api-key` / `Authorization: Bearer`), are wrapped in `pydantic.SecretStr`, and are redacted from logs/errors.
* **Strict SSRF Protection:** Cloud providers are pinned to an HTTPS-only allowlist; local LLMs are restricted to loopback (`127.0.0.1` / `localhost` / `::1`) with DNS rebinding, IMDS (`169.254.169.254`), and non-global IP blocking plus `follow_redirects=False`.
* **XSS & CSP Hardening:** Strict `Content-Security-Policy` (`script-src 'self'`), Mermaid `securityLevel: "strict"` with `htmlLabels: false`, unconditional stripping of `click`/`%%{init}` directives and HTML/JS payloads, and `innerHTML`-free DOM rendering.
* **Isolated Static Serving:** Static assets are served exclusively from `static/` with canonical path confinement (`Path.resolve().is_relative_to()`).

---

## License

Released under the **MIT License**. See [LICENSE](LICENSE).
