"""Cliente HTTP unificado para proveedores Cloud (2026) y Locales (Ollama / LM Studio).

Características de seguridad obligatorias:
- Validación SSRF previa en toda petición (whitelist cloud + loopback-only local).
- `follow_redirects=False` para impedir bypass SSRF por 301/302.
- API keys enviadas EXCLUSIVAMENTE en cabeceras HTTP (nunca en query params).
- Lectura en streaming estrictamente acotada (MAX_LLM_RESPONSE_BYTES) anti-OOM.
- Errores mapeados de forma segura con redacción automática de credenciales.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from alvea.ai.catalog import ProviderSpec, StructuredMode, get_provider
from alvea.config import SETTINGS
from alvea.security import (
    CLOUD_HOST_ALLOWLIST,
    SSRFBlockedError,
    redact_secrets,
    validate_model_id,
    validate_outbound_url,
)


class ProviderCallError(RuntimeError):
    """Error controlado en la comunicación con un proveedor LLM."""

    def __init__(self, message: str, *, status_code: int = 502, retryable_mode: bool = False) -> None:
        super().__init__(redact_secrets(message))
        self.status_code = status_code
        self.retryable_mode = retryable_mode


def _resolve_api_key(provider: ProviderSpec, explicit_key: str | None) -> str:
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()
    if provider.env_var:
        return os.getenv(provider.env_var, "").strip()
    return ""


def _read_bounded_json(response: httpx.Response) -> dict[str, Any]:
    """Lee el cuerpo JSON acotado en memoria (soporta streaming y mocks estándar)."""
    if hasattr(response, "iter_bytes") and callable(response.iter_bytes):
        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in response.iter_bytes():
                if not chunk:
                    continue
                total += len(chunk)
                if total > SETTINGS.max_llm_response_bytes:
                    raise ProviderCallError(
                        "La respuesta del proveedor excedió el tamaño máximo permitido.",
                        status_code=502,
                    )
                chunks.append(chunk)
            raw = b"".join(chunks)
        except httpx.ResponseNotRead:
            raw = response.content
    else:
        raw = response.content

    if len(raw) > SETTINGS.max_llm_response_bytes:
        raise ProviderCallError("La respuesta del proveedor excedió el tamaño máximo permitido.", status_code=502)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderCallError("El proveedor devolvió una respuesta no JSON inválida.", status_code=502) from exc


def _resolve_provider_url(provider: ProviderSpec, custom_base_url: str | None) -> tuple[str, str]:
    """Devuelve (base_url_validada, ssrf_mode)."""
    if provider.group == "local":
        base = (custom_base_url or provider.default_base_url or "").strip().rstrip("/")
        validated = validate_outbound_url(base, mode="local")
        return validated, "local"

    if provider.id == "custom_openai":
        base = (custom_base_url or "").strip().rstrip("/")
        if not base:
            raise ProviderCallError("Debes indicar una URL base para el proveedor OpenAI personalizado.", status_code=400)
        validated = validate_outbound_url(base, mode="custom")
        return validated, "custom"

    expected_host = CLOUD_HOST_ALLOWLIST.get(provider.id)
    base = (provider.default_base_url or "").strip().rstrip("/")
    validated = validate_outbound_url(base, mode="cloud", expected_host=expected_host)
    return validated, "cloud"


def discover_local_models(provider_id: str, custom_base_url: str | None = None) -> dict[str, Any]:
    """Descubre modelos instalados en Ollama (/api/tags) o LM Studio (/v1/models)."""
    provider = get_provider(provider_id)
    if provider is None or not provider.supports_discovery:
        return {"ok": False, "models": [], "detail": "Este proveedor no soporta autodescubrimiento local."}

    try:
        base_url, _ = _resolve_provider_url(provider, custom_base_url)
    except SSRFBlockedError as exc:
        return {"ok": False, "models": [], "detail": str(exc)}

    timeout = httpx.Timeout(connect=SETTINGS.local_probe_timeout_s, read=3.0, write=2.0, pool=2.0)

    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            if provider.protocol == "ollama":
                endpoint = f"{base_url}/api/tags"
                with client.stream("GET", endpoint) as resp:
                    if resp.status_code != 200:
                        return {"ok": False, "models": [], "detail": f"Ollama respondió HTTP {resp.status_code}."}
                    data = _read_bounded_json(resp)
                models = []
                for item in data.get("models", []):
                    name = str(item.get("name") or "").strip()
                    if not name:
                        continue
                    details = item.get("details") or {}
                    param_size = details.get("parameter_size") or ""
                    quant = details.get("quantization_level") or ""
                    size_gb = round(float(item.get("size", 0)) / (1024**3), 1) if item.get("size") else None
                    meta_parts = [p for p in (param_size, quant, f"{size_gb} GB" if size_gb else "") if p]
                    models.append({
                        "id": name,
                        "label": f"{name} ({', '.join(meta_parts)})" if meta_parts else name,
                        "installed": True,
                        "badges": ["Instalado", "Local"],
                    })
                return {
                    "ok": True,
                    "models": models,
                    "detail": f"{len(models)} modelo(s) detectado(s) en Ollama.",
                }

            endpoint = f"{base_url}/models" if base_url.endswith("/v1") else f"{base_url}/v1/models"
            with client.stream("GET", endpoint) as resp:
                if resp.status_code != 200:
                    return {"ok": False, "models": [], "detail": f"El servidor local respondió HTTP {resp.status_code}."}
                data = _read_bounded_json(resp)
            models = []
            for item in data.get("data", []):
                mid = str(item.get("id") or "").strip()
                if mid:
                    models.append({
                        "id": mid,
                        "label": f"{mid} (Local)",
                        "installed": True,
                        "badges": ["Cargado", "Local"],
                    })
            return {
                "ok": True,
                "models": models,
                "detail": f"{len(models)} modelo(s) detectado(s) en servidor local.",
            }
    except httpx.ConnectError:
        return {
            "ok": False,
            "models": [],
            "detail": f"No se detectó ningún servicio escuchando en {base_url}. Inicia {provider.name} primero.",
        }
    except httpx.TimeoutException:
        return {"ok": False, "models": [], "detail": f"Tiempo de espera agotado al consultar {base_url}."}
    except Exception:
        return {"ok": False, "models": [], "detail": "Error inesperado al consultar modelos locales."}


def call_llm_provider(
    *,
    provider: ProviderSpec,
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    json_schema: dict[str, Any],
    mode: StructuredMode,
    api_key: str | None = None,
    custom_base_url: str | None = None,
    temperature: float = 0.1,
) -> tuple[str, dict[str, Any]]:
    """Ejecuta la llamada HTTP hacia el proveedor LLM seleccionado bajo políticas estrictas."""
    safe_model = validate_model_id(model_id)
    base_url, ssrf_mode = _resolve_provider_url(provider, custom_base_url)
    resolved_key = _resolve_api_key(provider, api_key)

    if provider.requires_api_key and not resolved_key:
        raise ProviderCallError(
            f"Falta la API Key para {provider.name}. Configúrala en 'Proveedores IA' o en la variable {provider.env_var}.",
            status_code=401,
        )

    timeout = httpx.Timeout(
        connect=SETTINGS.connect_timeout_s,
        read=SETTINGS.read_timeout_s,
        write=10.0,
        pool=5.0,
    )
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)

    try:
        with httpx.Client(timeout=timeout, limits=limits, follow_redirects=False) as client:
            if provider.protocol == "gemini":
                return _call_gemini(
                    client, base_url, safe_model, resolved_key, system_prompt, user_prompt, json_schema, mode, temperature
                )
            if provider.protocol == "ollama":
                return _call_ollama(
                    client, base_url, safe_model, system_prompt, user_prompt, json_schema, mode, temperature
                )
            if provider.protocol == "anthropic":
                return _call_anthropic(
                    client, base_url, safe_model, resolved_key, system_prompt, user_prompt, json_schema, mode, temperature
                )
            return _call_openai_compat(
                client,
                provider,
                base_url,
                safe_model,
                resolved_key,
                system_prompt,
                user_prompt,
                json_schema,
                mode,
                temperature,
                ssrf_mode,
            )
    except ProviderCallError:
        raise
    except httpx.TimeoutException as exc:
        raise ProviderCallError(f"Tiempo de espera agotado al contactar a {provider.name}.", status_code=504) from exc
    except httpx.ConnectError as exc:
        raise ProviderCallError(f"No se pudo conectar con {provider.name}. Verifica red o servicio local.", status_code=502) from exc
    except httpx.HTTPError as exc:
        raise ProviderCallError(f"Error de transporte HTTP con {provider.name}.", status_code=502) from exc


def _post_bounded_json(
    client: httpx.Client,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    provider_name: str,
) -> dict[str, Any]:
    """Ejecuta POST con lectura acotada en streaming anti-OOM."""
    with client.stream("POST", url, headers=headers, json=payload) as resp:
        _check_http_status(resp, provider_name)
        return _read_bounded_json(resp)


def _call_gemini(
    client: httpx.Client,
    base_url: str,
    model_id: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    json_schema: dict[str, Any],
    mode: StructuredMode,
    temperature: float,
) -> tuple[str, dict[str, Any]]:
    # API key SIEMPRE en cabecera x-goog-api-key, NUNCA en query string
    url = f"{base_url}/v1beta/models/{model_id}:generateContent"
    gen_cfg: dict[str, Any] = {"temperature": temperature, "maxOutputTokens": 4096}
    if mode == "json_schema":
        gen_cfg["responseMimeType"] = "application/json"
        gen_cfg["responseJsonSchema"] = json_schema
    elif mode == "json_object":
        gen_cfg["responseMimeType"] = "application/json"

    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": gen_cfg,
    }
    data = _post_bounded_json(
        client,
        url,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        payload=payload,
        provider_name="Google Gemini",
    )
    candidates = data.get("candidates") or []
    parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
    text = "".join(str(p.get("text") or "") for p in parts if isinstance(p, dict))
    if not text.strip():
        raise ProviderCallError("Google Gemini devolvió una respuesta vacía o filtrada.", status_code=502)
    return text, {"usage": data.get("usageMetadata") or {}}


def _call_ollama(
    client: httpx.Client,
    base_url: str,
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    json_schema: dict[str, Any],
    mode: StructuredMode,
    temperature: float,
) -> tuple[str, dict[str, Any]]:
    url = f"{base_url}/api/chat"
    payload: dict[str, Any] = {
        "model": model_id,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "options": {"temperature": temperature, "num_ctx": 8192},
    }
    if mode == "json_schema":
        payload["format"] = json_schema
    elif mode == "json_object":
        payload["format"] = "json"

    data = _post_bounded_json(
        client,
        url,
        headers={"Content-Type": "application/json"},
        payload=payload,
        provider_name="Ollama Local",
    )
    content = (data.get("message") or {}).get("content")
    text = content if isinstance(content, str) else ""
    if not text.strip():
        raise ProviderCallError("Ollama devolvió una respuesta vacía.", status_code=502)
    return text, {"eval_count": data.get("eval_count")}


def _call_anthropic(
    client: httpx.Client,
    base_url: str,
    model_id: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    json_schema: dict[str, Any],
    mode: StructuredMode,
    temperature: float,
) -> tuple[str, dict[str, Any]]:
    url = f"{base_url}/v1/messages"
    payload: dict[str, Any] = {
        "model": model_id,
        "max_tokens": 4096,
        "temperature": temperature,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    if mode == "json_schema":
        payload["tools"] = [
            {
                "name": "emit_process_graph",
                "description": "Emite el objeto JSON ProcessGraph estructurado.",
                "input_schema": json_schema,
            }
        ]
        payload["tool_choice"] = {"type": "tool", "name": "emit_process_graph"}

    data = _post_bounded_json(
        client,
        url,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        payload=payload,
        provider_name="Anthropic",
    )
    blocks = data.get("content") or []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "tool_use" and isinstance(block.get("input"), dict):
            return json.dumps(block["input"], ensure_ascii=False), {"usage": data.get("usage") or {}}
    text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
    if not text.strip():
        raise ProviderCallError("Anthropic devolvió una respuesta vacía.", status_code=502)
    return text, {"usage": data.get("usage") or {}}


def _call_openai_compat(
    client: httpx.Client,
    provider: ProviderSpec,
    base_url: str,
    model_id: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    json_schema: dict[str, Any],
    mode: StructuredMode,
    temperature: float,
    ssrf_mode: str,
) -> tuple[str, dict[str, Any]]:
    effective_model = model_id
    if provider.id == "groq" and model_id == "gpt-oss-120b":
        effective_model = "openai/gpt-oss-120b"

    if provider.id == "lmstudio" and not base_url.endswith("/v1"):
        url = f"{base_url}/v1/chat/completions"
    else:
        url = f"{base_url}/chat/completions"

    if ssrf_mode == "cloud":
        validate_outbound_url(url, mode="cloud", expected_host=CLOUD_HOST_ALLOWLIST.get(provider.id), resolve_dns=False)

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    elif provider.id == "lmstudio":
        headers["Authorization"] = "Bearer lm-studio"

    if provider.id == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/ASRtech-dev/Alvea"
        headers["X-Title"] = "ALVEA Process Architecture Studio"

    is_openai_reasoning = provider.id == "openai" and effective_model.startswith(("o1", "o3", "o4"))
    payload: dict[str, Any] = {
        "model": effective_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if is_openai_reasoning:
        payload["max_completion_tokens"] = 4096
    else:
        payload["temperature"] = temperature
        payload["max_tokens"] = 4096

    if mode == "json_schema":
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "process_graph",
                "strict": False,
                "schema": json_schema,
            },
        }
    elif mode == "json_object":
        payload["response_format"] = {"type": "json_object"}

    data = _post_bounded_json(
        client,
        url,
        headers=headers,
        payload=payload,
        provider_name=provider.name,
    )
    choices = data.get("choices") or []
    raw_content = ((choices[0].get("message") or {}).get("content")) if choices else None
    text = raw_content if isinstance(raw_content, str) else ""
    if not text.strip():
        raise ProviderCallError(f"{provider.name} devolvió una respuesta vacía.", status_code=502)
    return text, {"usage": data.get("usage") or {}}


def _check_http_status(resp: httpx.Response, provider_name: str) -> None:
    if 300 <= resp.status_code < 400:
        raise ProviderCallError(f"Redirección HTTP bloqueada por política de seguridad en {provider_name}.", status_code=502)
    if resp.status_code in (401, 403):
        raise ProviderCallError(f"Credenciales rechazadas por {provider_name} (HTTP {resp.status_code}). Verifica tu API Key.", status_code=401)
    if resp.status_code == 429:
        raise ProviderCallError(f"Límite de cuota o velocidad alcanzado en {provider_name} (HTTP 429).", status_code=429)
    if resp.status_code in (400, 422):
        raise ProviderCallError(
            f"{provider_name} rechazó el formato estructurado (HTTP {resp.status_code}).",
            status_code=400,
            retryable_mode=True,
        )
    if resp.status_code >= 400:
        raise ProviderCallError(f"Error remoto en {provider_name} (HTTP {resp.status_code}).", status_code=502)
