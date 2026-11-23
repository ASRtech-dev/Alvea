"""2026 Multi-Vendor AI Provider Catalog (Local Zero-API, Free Cloud Tiers & BYOK)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

ProviderGroup = Literal["local", "free_cloud", "byok"]
StructuredMode = Literal["native", "json_schema", "json_object", "prompt_only"]


@dataclass(frozen=True, slots=True)
class ModelSpec:
    id: str
    label: str
    badges: tuple[str, ...] = ()
    structured_mode: StructuredMode = "json_object"
    has_reasoning_tags: bool = False
    compact_prompt: bool = False
    recommended: bool = False
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    id: str
    name: str
    company: str
    group: ProviderGroup
    protocol: Literal["native", "gemini", "openai_compat", "ollama", "anthropic"]
    default_base_url: str | None
    requires_api_key: bool
    env_var: str | None
    supports_discovery: bool = False
    allow_custom_url: bool = False
    badges: tuple[str, ...] = ()
    privacy_note: str = ""
    key_hint: str = ""
    default_model: str = ""
    models: tuple[ModelSpec, ...] = field(default_factory=tuple)

    def to_public_dict(self) -> dict:
        data = asdict(self)
        data["badges"] = list(self.badges)
        data["models"] = [
            {**asdict(m), "badges": list(m.badges)} for m in self.models
        ]
        return data


PROVIDER_CATALOG: tuple[ProviderSpec, ...] = (
    # ─── 1. LOCAL / ZERO CLOUD API ──────────────────────────────────────────────
    ProviderSpec(
        id="native_python",
        name="Native Python BPA Engine",
        company="ALVEA (Local)",
        group="local",
        protocol="native",
        default_base_url=None,
        requires_api_key=False,
        env_var=None,
        supports_discovery=False,
        badges=("Local", "No API", "Free", "Offline"),
        privacy_note="100% deterministic local execution in Python + NetworkX. No data ever leaves your machine.",
        default_model="alvea-bpa-v3",
        models=(
            ModelSpec(
                id="alvea-bpa-v3",
                label="ALVEA Deterministic Workflow Engine v3 (NLP + NetworkX)",
                badges=("Offline", "Instant", "No API"),
                structured_mode="native",
                recommended=True,
                notes="Extracts actors, parallel fork/join blocks, multi-branch decisions, SLAs, and rework loops in English/Spanish without an LLM.",
            ),
        ),
    ),
    ProviderSpec(
        id="ollama",
        name="Ollama (Local LLM)",
        company="Ollama",
        group="local",
        protocol="ollama",
        default_base_url="http://127.0.0.1:11434",
        requires_api_key=False,
        env_var=None,
        supports_discovery=True,
        allow_custom_url=True,
        badges=("Local", "No API", "Free", "Private"),
        privacy_note="Runs locally on your CPU/GPU via Ollama. Supports live model auto-discovery (/api/tags).",
        default_model="gemma4:12b",
        models=(
            ModelSpec("qwen3.8:27b", "Qwen 3.8 27B (Alibaba)", ("Local", "Recommended 24GB"), "json_schema", True, False, True),
            ModelSpec("qwen3-coder:30b", "Qwen 3 Coder 30B MoE (Alibaba)", ("Local", "Precise JSON"), "json_schema", True, False, False),
            ModelSpec("gemma4:12b", "Gemma 4 12B (Google Open)", ("Local", "Balanced"), "json_schema", False, False, True),
            ModelSpec("gemma4:e4b", "Gemma 4 E4B (Edge / Laptop)", ("Local", "Lightweight"), "json_object", False, True, False),
            ModelSpec("llama3.3:70b", "Llama 3.3 70B (Meta)", ("Local", "High Capacity"), "json_object", False, False, False),
            ModelSpec("llama3.1:8b", "Llama 3.1 8B (Meta)", ("Local", "8GB RAM"), "json_object", False, True, False),
            ModelSpec("llama3.2:3b", "Llama 3.2 3B (Meta)", ("Local", "Fast CPU"), "json_object", False, True, False),
            ModelSpec("deepseek-r1:8b", "DeepSeek-R1 8B (Reasoning)", ("Local", "Chain-of-Thought"), "json_object", True, True, False),
        ),
    ),
    ProviderSpec(
        id="lmstudio",
        name="LM Studio / Local OpenAI",
        company="LM Studio / llama.cpp",
        group="local",
        protocol="openai_compat",
        default_base_url="http://127.0.0.1:1234/v1",
        requires_api_key=False,
        env_var=None,
        supports_discovery=True,
        allow_custom_url=True,
        badges=("Local", "No API", "Free", "Private"),
        privacy_note="Connects to LM Studio, llama-server, Jan, or local vLLM with auto-discovery (/v1/models).",
        default_model="local-model",
        models=(
            ModelSpec("local-model", "Active LM Studio Model (click Auto-Discover)", ("Local",), "json_object", False, False, True),
        ),
    ),

    # ─── 2. FREE CLOUD PROVIDERS (MULTI-VENDOR 2026) ────────────────────────────
    ProviderSpec(
        id="gemini",
        name="Google Gemini (AI Studio)",
        company="Google",
        group="free_cloud",
        protocol="gemini",
        default_base_url="https://generativelanguage.googleapis.com",
        requires_api_key=True,
        env_var="GEMINI_API_KEY",
        badges=("Free", "Free Tier", "Strict JSON"),
        privacy_note="Google AI Studio free tier with no credit card required. Use Local mode for confidential workflows.",
        key_hint="Get a free API key at aistudio.google.com/apikey",
        default_model="gemini-3.8-flash",
        models=(
            ModelSpec("gemini-3.8-flash", "Gemini 3.8 Flash", ("Free", "Recommended"), "json_schema", False, False, True),
            ModelSpec("gemini-3.5-flash", "Gemini 3.5 Flash", ("Free", "Stable"), "json_schema", False, False, False),
            ModelSpec("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", ("Free", "Ultra-fast"), "json_schema", False, False, False),
            ModelSpec("gemini-2.5-flash", "Gemini 2.5 Flash", ("Free", "Classic"), "json_schema", False, False, False),
        ),
    ),
    ProviderSpec(
        id="groq",
        name="Groq Cloud (LPU)",
        company="Groq / Meta / Qwen / OpenAI OSS",
        group="free_cloud",
        protocol="openai_compat",
        default_base_url="https://api.groq.com/openai/v1",
        requires_api_key=True,
        env_var="GROQ_API_KEY",
        badges=("Free", "Ultra-fast"),
        privacy_note="Free LPU inference tier with no credit card required (minute/day rate limits apply).",
        key_hint="Get a free API key at console.groq.com/keys",
        default_model="llama-3.3-70b-versatile",
        models=(
            ModelSpec("llama-3.3-70b-versatile", "Meta Llama 3.3 70B Versatile", ("Free", "Recommended"), "json_object", False, False, True),
            ModelSpec("qwen/qwen3.8-27b", "Alibaba Qwen 3.8 27B", ("Free", "Reasoning"), "json_schema", True, False, True),
            ModelSpec("openai/gpt-oss-120b", "OpenAI GPT-OSS 120B", ("Free", "High Capacity"), "json_schema", True, False, False),
            ModelSpec("llama-3.1-8b-instant", "Meta Llama 3.1 8B Instant", ("Free", "High Quota"), "json_object", False, True, False),
        ),
    ),
    ProviderSpec(
        id="openrouter",
        name="OpenRouter (:free)",
        company="Multi-Vendor (Google, Qwen, NVIDIA)",
        group="free_cloud",
        protocol="openai_compat",
        default_base_url="https://openrouter.ai/api/v1",
        requires_api_key=True,
        env_var="OPENROUTER_API_KEY",
        badges=("Free", "Multi-Vendor"),
        privacy_note="Zero-cost ($0) pool of open models across multiple labs with automatic fallback routing.",
        key_hint="Get a free API key at openrouter.ai/keys",
        default_model="openrouter/free",
        models=(
            ModelSpec("openrouter/free", "OpenRouter Auto-Router (:free)", ("Free", "Resilient"), "json_object", False, False, True),
            ModelSpec("google/gemma-4-31b-it:free", "Google Gemma 4 31B IT (:free)", ("Free", "Google"), "json_object", False, False, True),
            ModelSpec("google/gemma-4-26b-a4b-it:free", "Google Gemma 4 26B A4B (:free)", ("Free", "Fast MoE"), "json_object", False, False, False),
            ModelSpec("qwen/qwen3.8-27b:free", "Alibaba Qwen 3.8 27B (:free)", ("Free", "Qwen"), "json_object", True, False, False),
            ModelSpec("nvidia/nemotron-3.5-lightning:free", "NVIDIA Nemotron 3.5 Lightning (:free)", ("Free", "NVIDIA"), "json_object", True, False, False),
            ModelSpec("nvidia/nemotron-3-ultra-550b-a55b:free", "NVIDIA Nemotron 3 Ultra 550B (:free)", ("Free", "NVIDIA"), "json_object", True, False, False),
        ),
    ),
    ProviderSpec(
        id="cerebras",
        name="Cerebras Inference",
        company="Cerebras / Qwen / OpenAI OSS",
        group="free_cloud",
        protocol="openai_compat",
        default_base_url="https://api.cerebras.ai/v1",
        requires_api_key=True,
        env_var="CEREBRAS_API_KEY",
        badges=("Free Trial", "Ultra-fast"),
        privacy_note="Wafer-scale inference (>1000 tok/s) with native structured JSON decoding.",
        key_hint="Get an API key at cloud.cerebras.ai",
        default_model="qwen-3.8-27b",
        models=(
            ModelSpec("qwen-3.8-27b", "Qwen 3.8 27B (Cerebras)", ("Ultra-fast", "Recommended"), "json_schema", True, False, True),
            ModelSpec("gpt-oss-120b", "GPT-OSS 120B (Cerebras)", ("Ultra-fast", "120B"), "json_schema", True, False, False),
        ),
    ),
    ProviderSpec(
        id="github_models",
        name="GitHub Models",
        company="GitHub (OpenAI, Meta, DeepSeek, Mistral)",
        group="free_cloud",
        protocol="openai_compat",
        default_base_url="https://models.github.ai/inference",
        requires_api_key=True,
        env_var="GITHUB_TOKEN",
        badges=("Free Dev", "Multi-Vendor"),
        privacy_note="Free for developers using a GitHub Personal Access Token with models:read scope.",
        key_hint="Create a GitHub PAT with models:read at github.com/settings/tokens",
        default_model="openai/gpt-4.1-mini",
        models=(
            ModelSpec("openai/gpt-4.1-mini", "OpenAI GPT-4.1 Mini (GitHub)", ("Free Dev", "Recommended"), "json_schema", False, False, True),
            ModelSpec("meta/llama-3.3-70b-instruct", "Meta Llama 3.3 70B Instruct", ("Free Dev", "Meta"), "json_object", False, False, False),
            ModelSpec("deepseek/deepseek-r1", "DeepSeek-R1 (GitHub)", ("Free Dev", "Reasoning"), "prompt_only", True, False, False),
            ModelSpec("mistral-ai/mistral-small-2503", "Mistral Small 2503", ("Free Dev", "Mistral"), "json_object", False, False, False),
        ),
    ),

    # ─── 3. OTHER / BYOK PROVIDERS ──────────────────────────────────────────────
    ProviderSpec(
        id="mistral",
        name="Mistral AI (La Plateforme)",
        company="Mistral AI",
        group="byok",
        protocol="openai_compat",
        default_base_url="https://api.mistral.ai/v1",
        requires_api_key=True,
        env_var="MISTRAL_API_KEY",
        badges=("BYOK", "European"),
        privacy_note="Commercial Mistral AI API (requires an API key with active billing).",
        key_hint="Get an API key at console.mistral.ai/api-keys",
        default_model="mistral-small-latest",
        models=(
            ModelSpec("mistral-small-latest", "Mistral Small Latest", ("BYOK", "Efficient"), "json_object", False, False, True),
            ModelSpec("mistral-large-latest", "Mistral Large Latest", ("BYOK", "Flagship"), "json_object", False, False, False),
        ),
    ),
    ProviderSpec(
        id="openai",
        name="OpenAI API",
        company="OpenAI",
        group="byok",
        protocol="openai_compat",
        default_base_url="https://api.openai.com/v1",
        requires_api_key=True,
        env_var="OPENAI_API_KEY",
        badges=("BYOK", "Strict JSON"),
        privacy_note="Direct OpenAI API with native Structured Outputs.",
        key_hint="Get an API key at platform.openai.com/api-keys",
        default_model="gpt-4.1-mini",
        models=(
            ModelSpec("gpt-4.1-mini", "GPT-4.1 Mini", ("BYOK", "Recommended"), "json_schema", False, False, True),
            ModelSpec("gpt-4.1", "GPT-4.1", ("BYOK", "Advanced"), "json_schema", False, False, False),
            ModelSpec("o4-mini", "o4-mini (Reasoning)", ("BYOK", "Reasoning"), "json_schema", False, False, False),
        ),
    ),
    ProviderSpec(
        id="anthropic",
        name="Anthropic Claude",
        company="Anthropic",
        group="byok",
        protocol="anthropic",
        default_base_url="https://api.anthropic.com",
        requires_api_key=True,
        env_var="ANTHROPIC_API_KEY",
        badges=("BYOK", "High Precision"),
        privacy_note="Anthropic Messages API with structured tool_use output.",
        key_hint="Get an API key at console.anthropic.com/settings/keys",
        default_model="claude-sonnet-4-5",
        models=(
            ModelSpec("claude-sonnet-4-5", "Claude Sonnet 4.5", ("BYOK", "Recommended"), "json_schema", False, False, True),
            ModelSpec("claude-haiku-4-5", "Claude Haiku 4.5", ("BYOK", "Fast"), "json_schema", False, False, False),
        ),
    ),
    ProviderSpec(
        id="custom_openai",
        name="Custom API Endpoint",
        company="Custom",
        group="byok",
        protocol="openai_compat",
        default_base_url="",
        requires_api_key=False,
        env_var="CUSTOM_API_KEY",
        allow_custom_url=True,
        badges=("Custom", "Multi-Protocol"),
        privacy_note="Connect any public HTTPS API or local loopback server (vLLM, LiteLLM, DeepSeek, Together, Fireworks, custom Gemini/Anthropic gateways) under SSRF protection.",
        key_hint="Provide your endpoint Base URL, protocol, model ID, and optional API key.",
        default_model="custom-model",
        models=(
            ModelSpec("custom-model", "Custom model (editable)", ("Custom",), "json_object", False, False, True),
        ),
    ),
)

PROVIDER_BY_ID: dict[str, ProviderSpec] = {p.id: p for p in PROVIDER_CATALOG}


def get_provider(provider_id: str) -> ProviderSpec | None:
    return PROVIDER_BY_ID.get((provider_id or "").strip().lower())


def get_model_spec(provider: ProviderSpec, model_id: str) -> ModelSpec | None:
    for m in provider.models:
        if m.id == model_id:
            return m
    return None


def catalog_as_json() -> list[dict]:
    return [p.to_public_dict() for p in PROVIDER_CATALOG]
