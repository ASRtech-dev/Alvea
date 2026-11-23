"""Protección estricta contra SSRF, DNS Rebinding e inyección en rutas de modelo."""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

from alvea.config import SETTINGS


class SSRFBlockedError(ValueError):
    """Error lanzado cuando una URL o modelo viola las políticas anti-SSRF."""


# Lista blanca estricta de hosts cloud permitidos (HTTPS obligatorio, puerto 443)
CLOUD_HOST_ALLOWLIST: dict[str, str] = {
    "gemini": "generativelanguage.googleapis.com",
    "groq": "api.groq.com",
    "openrouter": "openrouter.ai",
    "cerebras": "api.cerebras.ai",
    "github_models": "models.github.ai",
    "mistral": "api.mistral.ai",
    "openai": "api.openai.com",
    "anthropic": "api.anthropic.com",
}

LOCAL_PROVIDERS: frozenset[str] = frozenset({"ollama", "lmstudio"})
LOCAL_HOSTNAMES: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})
BLOCKED_METADATA_HOSTS: frozenset[str] = frozenset({
    "metadata.google.internal",
    "metadata",
    "169.254.169.254",
    "169.254.170.2",
    "100.100.100.200",
    "fd00:ec2::254",
})

MODEL_ID_REGEX = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:/@-]{0,119}$")


def validate_model_id(model_id: str) -> str:
    """Valida estrictamente el identificador de modelo para evitar Path/Query Injection."""
    cleaned = (model_id or "").strip()
    if not cleaned:
        raise SSRFBlockedError("El identificador del modelo no puede estar vacío.")
    if ".." in cleaned or "?" in cleaned or "#" in cleaned or "%" in cleaned or "\\" in cleaned:
        raise SSRFBlockedError("El identificador del modelo contiene caracteres prohibidos.")
    if not MODEL_ID_REGEX.fullmatch(cleaned):
        raise SSRFBlockedError("Formato de identificador de modelo inválido.")
    return cleaned


def _unwrap_ip(raw_ip: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    addr = ipaddress.ip_address(raw_ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return addr.ipv4_mapped
    return addr


def _is_forbidden_remote_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        not addr.is_global
        or addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
        or str(addr) in BLOCKED_METADATA_HOSTS
    )


def _resolve_host_ips(hostname: str, port: int) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    # Si ya es una IP literal, parsear directamente sin DNS
    try:
        return [_unwrap_ip(hostname)]
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFBlockedError(f"No se pudo resolver el host '{hostname}'.") from exc

    ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        sockaddr = info[4]
        if sockaddr:
            ips.append(_unwrap_ip(str(sockaddr[0])))
    if not ips:
        raise SSRFBlockedError(f"Resolución DNS vacía para '{hostname}'.")
    return ips


def validate_outbound_url(
    url: str,
    *,
    mode: str = "remote",
    expected_host: str | None = None,
    resolve_dns: bool = True,
) -> str:
    """Valida una URL saliente contra ataques SSRF y DNS rebinding.

    mode:
      - "cloud": HTTPS obligatorio, puerto 443, host exacto en whitelist, solo IPs públicas.
      - "local": HTTP o HTTPS solo hacia loopback (127.0.0.1 / ::1 / localhost), puerto >= 1024.
      - "custom": HTTPS hacia hosts públicos (o HTTP solo si es loopback explícito, puerto >= 1024).
    """
    raw = (url or "").strip()
    if not raw or any(ch in raw for ch in ("\r", "\n", "\x00", " ")):
        raise SSRFBlockedError("URL vacía o con caracteres de control prohibidos.")

    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise SSRFBlockedError(f"Esquema de URL no permitido: '{scheme}'.")

    if parsed.username or parsed.password:
        raise SSRFBlockedError("No se permiten credenciales embebidas en la URL.")
    if parsed.fragment:
        raise SSRFBlockedError("No se permiten fragmentos en la URL saliente.")

    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not hostname:
        raise SSRFBlockedError("Host ausente en la URL.")
    if hostname in BLOCKED_METADATA_HOSTS:
        raise SSRFBlockedError("Acceso bloqueado a host de metadatos cloud.")

    try:
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise SSRFBlockedError("Puerto inválido en la URL.") from exc

    if mode == "cloud":
        if scheme != "https" or port != 443:
            raise SSRFBlockedError("Los proveedores cloud requieren estrictamente HTTPS en puerto 443.")
        if expected_host and hostname != expected_host.lower():
            raise SSRFBlockedError("El host no coincide con la lista blanca del proveedor.")
        if resolve_dns:
            for ip in _resolve_host_ips(hostname, port):
                if _is_forbidden_remote_ip(ip):
                    raise SSRFBlockedError("El host resolvió a una dirección IP no pública prohibida.")
        return raw

    if mode == "local":
        allowed_hosts = set(LOCAL_HOSTNAMES)
        if SETTINGS.allow_docker_host:
            allowed_hosts.add("host.docker.internal")
        if hostname not in allowed_hosts:
            raise SSRFBlockedError(
                "Los proveedores locales solo permiten conexiones hacia localhost / 127.0.0.1 / ::1."
            )
        if port < 1024 or port > 65535:
            raise SSRFBlockedError("Puerto local fuera del rango permitido (1024-65535).")
        if resolve_dns and hostname != "host.docker.internal":
            for ip in _resolve_host_ips(hostname, port):
                if not ip.is_loopback or ip.is_unspecified:
                    raise SSRFBlockedError("El host local resolvió fuera de loopback.")
        return raw

    if mode == "custom":
        is_local = hostname in LOCAL_HOSTNAMES
        if is_local:
            if port < 1024 or port > 65535:
                raise SSRFBlockedError("Puerto local fuera del rango permitido (1024-65535).")
            if resolve_dns:
                for ip in _resolve_host_ips(hostname, port):
                    if not ip.is_loopback or ip.is_unspecified:
                        raise SSRFBlockedError("Dirección local inválida.")
            return raw

        if scheme != "https":
            raise SSRFBlockedError("Endpoints remotos personalizados requieren HTTPS.")
        if port not in (443, 8443):
            raise SSRFBlockedError("Solo se permiten puertos HTTPS estándar (443/8443) en endpoints remotos.")
        if resolve_dns:
            for ip in _resolve_host_ips(hostname, port):
                if _is_forbidden_remote_ip(ip):
                    raise SSRFBlockedError("El endpoint personalizado resolvió a una red interna/privada bloqueada.")
        return raw

    raise SSRFBlockedError(f"Modo de validación SSRF desconocido: '{mode}'.")
