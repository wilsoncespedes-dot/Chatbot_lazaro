"""Validación anti-SSRF de las URLs de callback del canal genérico."""
from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Sequence
from urllib.parse import SplitResult, urlsplit

MAX_CALLBACK_URL_LENGTH = 2048
_CGNAT = ipaddress.ip_network("100.64.0.0/10")
Resolver = Callable[[str], Sequence[str]]


class CallbackUrlRejected(ValueError):
    """La URL de callback no es segura o no se puede validar."""


def _parse_address(address: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    return ipaddress.ip_address(address.split("%", 1)[0])


def system_resolver(host: str) -> list[str]:
    """Resuelve el host a sus direcciones IP (sin red en los tests)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return []
    addresses: list[str] = []
    for info in infos:
        address = info[4][0]
        if address not in addresses:
            addresses.append(address)
    return addresses


def is_blocked_address(address: str) -> bool:
    """R42: privada, loopback, link-local, no especificada, multicast, reservada."""
    ip = _parse_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT:
        return True
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_unspecified
        or ip.is_multicast
        or ip.is_reserved
    )


def _split_url(url: str, allow_private: bool) -> SplitResult:
    if not isinstance(url, str) or not url:
        raise CallbackUrlRejected("la URL de callback no es válida")
    if len(url) > MAX_CALLBACK_URL_LENGTH:
        raise CallbackUrlRejected("la URL de callback es demasiado larga")
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in url):
        raise CallbackUrlRejected("la URL de callback no es válida")
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise CallbackUrlRejected("la URL de callback no es válida") from exc
    scheme = parts.scheme.lower()
    allowed_schemes = {"https", "http"} if allow_private else {"https"}
    if scheme not in allowed_schemes or not parts.hostname:
        raise CallbackUrlRejected("la URL de callback no es válida")
    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        raise CallbackUrlRejected("la URL de callback no puede llevar credenciales")
    try:
        parts.port
    except ValueError as exc:
        raise CallbackUrlRejected("la URL de callback no es válida") from exc
    return parts


def validate_callback_url_syntax(url: str, allow_private: bool = False) -> str:
    """R34, R41: valida esquema, host, credenciales y longitud; devuelve el host."""
    return _split_url(url, allow_private).hostname or ""


def validate_callback_url(
    url: str, resolver: Resolver, allow_private: bool = False
) -> tuple[str, list[str]]:
    """R41-R44, R48: devuelve (host, direcciones todas públicas) o lanza."""
    parts = _split_url(url, allow_private)
    host = parts.hostname or ""
    try:
        literal = _parse_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        addresses = [str(literal)]
    else:
        try:
            addresses = [str(address) for address in resolver(host)]
        except OSError:
            addresses = []
        if not addresses:
            raise CallbackUrlRejected("el host de callback no resuelve")
    for address in addresses:
        try:
            blocked = is_blocked_address(address)
        except ValueError as exc:
            raise CallbackUrlRejected(
                "el host de callback resuelve a una dirección no válida"
            ) from exc
        if blocked and not allow_private:
            raise CallbackUrlRejected(
                "el host de callback resuelve a una dirección bloqueada"
            )
    return host, addresses
