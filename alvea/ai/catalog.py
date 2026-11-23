"""Catálogo actualizado 2026 de proveedores de IA gratuitos, locales sin API y BYOK."""

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
    # ─── 1. LOCALES / SIN API EN LA NUBE ─────────────────────────────────────────
    ProviderSpec(
        id="native_python",
        name="Motor Nativo Python BPA",
        company="ALVEA (Local)",
        group="local",
        protocol="native",
        default_base_url=None,
        requires_api_key=False,
        env_var=None,
        supports_discovery=False,
        badges=("Local", "Sin API", "Gratis", "Offline"),
        privacy_note="100% determinista y local en Python + NetworkX. Ningún dato sale de tu equipo.",
        default_model="alvea-bpa-v2",
        models=(
            ModelSpec(
                id="alvea-bpa-v2",
                label="ALVEA Motor Determinista BPA v2 (NLP + NetworkX)",
                badges=("Offline", "Instantáneo", "Sin API"),
                structured_mode="native",
                recommended=True,
                notes="Extrae actores, secuencias, decisiones y bucles en español/inglés sin necesidad de LLM.",
            ),
        ),
    ),
    ProviderSpec(
        id="ollama",
        name="Ollama (LLM Local)",
        company="Ollama",
        group="local",
        protocol="ollama",
        default_base_url="http://127.0.0.1:11434",
        requires_api_key=False,
        env_var=None,
        supports_discovery=True,
        allow_custom_url=True,
        badges=("Local", "Sin API", "Gratis", "Privado"),
        privacy_note="Ejecución local en tu CPU/GPU mediante Ollama. Soporta autodescubrimiento (/api/tags).",
        default_model="gemma4:12b",
        models=(
            ModelSpec("qwen3.8:27b", "Qwen 3.8 27B (Alibaba)", ("Local", "Recomendado 24GB"), "json_schema", True, False, True),
            ModelSpec("qwen3-coder:30b", "Qwen 3 Coder 30B MoE (Alibaba)", ("Local", "JSON Preciso"), "json_schema", True, False, False),
            ModelSpec("gemma4:12b", "Gemma 4 12B (Google Open)", ("Local", "Equilibrado"), "json_schema", False, False, True),
            ModelSpec("gemma4:e4b", "Gemma 4 E4B (Edge / Portátil)", ("Local", "Ligero"), "json_object", False, True, False),
            ModelSpec("llama3.3:70b", "Llama 3.3 70B (Meta)", ("Local", "Alta Capacidad"), "json_object", False, False, False),
            ModelSpec("llama3.1:8b", "Llama 3.1 8B (Meta)", ("Local", "8GB RAM"), "json_object", False, True, False),
            ModelSpec("llama3.2:3b", "Llama 3.2 3B (Meta)", ("Local", "CPU Rápido"), "json_object", False, True, False),
            ModelSpec("deepseek-r1:8b", "DeepSeek-R1 8B (Razonamiento)", ("Local", "Chain-of-Thought"), "json_object", True, True, False),
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
        badges=("Local", "Sin API", "Gratis", "Privado"),
        privacy_note="Conecta a LM Studio, llama-server, Jan o vLLM local con autodescubrimiento (/v1/models).",
        default_model="local-model",
        models=(
            ModelSpec("local-model", "Modelo activo en LM Studio (usa Autodescubrir)", ("Local",), "json_object", False, False, True),
        ),
    ),

    # ─── 2. PROVEEDORES CLOUD GRATUITOS (MULTI-COMPAÑÍA 2026) ───────────────────
    ProviderSpec(
        id="gemini",
        name="Google Gemini (AI Studio)",
        company="Google",
        group="free_cloud",
        protocol="gemini",
        default_base_url="https://generativelanguage.googleapis.com",
        requires_api_key=True,
        env_var="GEMINI_API_KEY",
        badges=("Gratis", "Free Tier", "JSON Estricto"),
        privacy_note="Capa gratuita de Google AI Studio sin tarjeta. Para datos confidenciales usa modo Local.",
        default_model="gemini-3.8-flash",
        models=(
            ModelSpec("gemini-3.8-flash", "Gemini 3.8 Flash", ("Gratis", "Recomendado"), "json_schema", False, False, True),
            ModelSpec("gemini-3.5-flash", "Gemini 3.5 Flash", ("Gratis", "Estable"), "json_schema", False, False, False),
            ModelSpec("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", ("Gratis", "Ultra rápido"), "json_schema", False, False, False),
            ModelSpec("gemini-2.5-flash", "Gemini 2.5 Flash", ("Gratis", "Clásico"), "json_schema", False, False, False),
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
        badges=("Gratis", "Ultra rápido"),
        privacy_note="Capa gratuita en LPU sin tarjeta de crédito con límites por minuto/día.",
        default_model="llama-3.3-70b-versatile",
        models=(
            ModelSpec("llama-3.3-70b-versatile", "Meta Llama 3.3 70B Versatile", ("Gratis", "Recomendado"), "json_object", False, False, True),
            ModelSpec("qwen/qwen3.8-27b", "Alibaba Qwen 3.8 27B", ("Gratis", "Razonamiento"), "json_schema", True, False, True),
            ModelSpec("openai/gpt-oss-120b", "OpenAI GPT-OSS 120B", ("Gratis", "Alta Capacidad"), "json_schema", True, False, False),
            ModelSpec("llama-3.1-8b-instant", "Meta Llama 3.1 8B Instant", ("Gratis", "Alta Cuota"), "json_object", False, True, False),
        ),
    ),
    ProviderSpec(
        id="openrouter",
        name="OpenRouter (:free)",
        company="Multi-Compañía (Google, Qwen, NVIDIA)",
        group="free_cloud",
        protocol="openai_compat",
        default_base_url="https://openrouter.ai/api/v1",
        requires_api_key=True,
        env_var="OPENROUTER_API_KEY",
        badges=("Gratis", "Multi-compañía"),
        privacy_note="Pool gratuito ($0) con modelos abiertos de múltiples laboratorios y meta-router automático.",
        default_model="openrouter/free",
        models=(
            ModelSpec("openrouter/free", "OpenRouter Auto-Router (:free)", ("Gratis", "Resiliente"), "json_object", False, False, True),
            ModelSpec("google/gemma-4-31b-it:free", "Google Gemma 4 31B IT (:free)", ("Gratis", "Google"), "json_object", False, False, True),
            ModelSpec("google/gemma-4-26b-a4b-it:free", "Google Gemma 4 26B A4B (:free)", ("Gratis", "MoE Rápido"), "json_object", False, False, False),
            ModelSpec("qwen/qwen3.8-27b:free", "Alibaba Qwen 3.8 27B (:free)", ("Gratis", "Qwen"), "json_object", True, False, False),
            ModelSpec("nvidia/nemotron-3.5-lightning:free", "NVIDIA Nemotron 3.5 Lightning (:free)", ("Gratis", "NVIDIA"), "json_object", True, False, False),
            ModelSpec("nvidia/nemotron-3-ultra-550b-a55b:free", "NVIDIA Nemotron 3 Ultra 550B (:free)", ("Gratis", "NVIDIA"), "json_object", True, False, False),
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
        badges=("Free Trial", "Ultra rápido"),
        privacy_note="Inferencia wafer-scale (>1000 tok/s) con decodificación JSON estructurada nativa.",
        default_model="qwen-3.8-27b",
        models=(
            ModelSpec("qwen-3.8-27b", "Qwen 3.8 27B (Cerebras)", ("Ultra rápido", "Recomendado"), "json_schema", True, False, True),
            ModelSpec("gpt-oss-120b", "GPT-OSS 120B (Cerebras)", ("Ultra rápido", "120B"), "json_schema", True, False, False),
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
        badges=("Gratis Dev", "Multi-compañía"),
        privacy_note="Gratuito para desarrolladores usando un GitHub Personal Access Token con permiso models:read.",
        default_model="openai/gpt-4.1-mini",
        models=(
            ModelSpec("openai/gpt-4.1-mini", "OpenAI GPT-4.1 Mini (GitHub)", ("Gratis Dev", "Recomendado"), "json_schema", False, False, True),
            ModelSpec("meta/llama-3.3-70b-instruct", "Meta Llama 3.3 70B Instruct", ("Gratis Dev", "Meta"), "json_object", False, False, False),
            ModelSpec("deepseek/deepseek-r1", "DeepSeek-R1 (GitHub)", ("Gratis Dev", "Razonamiento"), "prompt_only", True, False, False),
            ModelSpec("mistral-ai/mistral-small-2503", "Mistral Small 2503", ("Gratis Dev", "Mistral"), "json_object", False, False, False),
        ),
    ),

    # ─── 3. OTROS PROVEEDORES (BYOK / PERSONALIZADO) ────────────────────────────
    ProviderSpec(
        id="mistral",
        name="Mistral AI (La Plateforme)",
        company="Mistral AI",
        group="byok",
        protocol="openai_compat",
        default_base_url="https://api.mistral.ai/v1",
        requires_api_key=True,
        env_var="MISTRAL_API_KEY",
        badges=("BYOK", "Europeo"),
        privacy_note="API comercial de Mistral AI (requiere clave con facturación activa).",
        default_model="mistral-small-latest",
        models=(
            ModelSpec("mistral-small-latest", "Mistral Small Latest", ("BYOK", "Eficiente"), "json_object", False, False, True),
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
        badges=("BYOK", "JSON Estricto"),
        privacy_note="API directa de OpenAI con Structured Outputs nativo.",
        default_model="gpt-4.1-mini",
        models=(
            ModelSpec("gpt-4.1-mini", "GPT-4.1 Mini", ("BYOK", "Recomendado"), "json_schema", False, False, True),
            ModelSpec("gpt-4.1", "GPT-4.1", ("BYOK", "Avanzado"), "json_schema", False, False, False),
            ModelSpec("o4-mini", "o4-mini (Razonamiento)", ("BYOK", "Razonamiento"), "json_schema", False, False, False),
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
        badges=("BYOK", "Alta Precisión"),
        privacy_note="API Messages de Anthropic usando tool_use estructurado.",
        default_model="claude-sonnet-4-5",
        models=(
            ModelSpec("claude-sonnet-4-5", "Claude Sonnet 4.5", ("BYOK", "Recomendado"), "json_schema", False, False, True),
            ModelSpec("claude-haiku-4-5", "Claude Haiku 4.5", ("BYOK", "Rápido"), "json_schema", False, False, False),
        ),
    ),
    ProviderSpec(
        id="custom_openai",
        name="Endpoint OpenAI-Compatible",
        company="Personalizado",
        group="byok",
        protocol="openai_compat",
        default_base_url="",
        requires_api_key=False,
        env_var="CUSTOM_API_KEY",
        allow_custom_url=True,
        badges=("Personalizado", "OpenAI API"),
        privacy_note="Compatible con servidores HTTPS públicos o loopback local (vLLM, LiteLLM, etc.) bajo validación SSRF.",
        default_model="custom-model",
        models=(
            ModelSpec("custom-model", "Modelo personalizado (editable)", ("Personalizado",), "json_object", False, False, True),
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
