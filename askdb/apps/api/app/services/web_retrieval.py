"""Allowlisted, opt-in web retrieval with SSRF protections."""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx

from app.core.config import Settings
from app.core.exceptions import ValidationError
from app.services.knowledge import Citation


def _is_public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_web_url(url: str, allowlist: list[str]) -> str:
    """Validate scheme, allowlist, and resolved addresses before any request."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValidationError("Web retrieval only supports absolute HTTP(S) URLs.")
    host = parsed.hostname.rstrip(".").lower()
    allowed = {
        item.lower().removeprefix("http://").removeprefix("https://").split("/")[0]
        for item in allowlist
    }
    if not any(host == item or host.endswith(f".{item}") for item in allowed):
        raise ValidationError("The requested web host is not allowlisted.")
    if host == "localhost":
        raise ValidationError("Private and local web hosts are not allowed.")
    try:
        addresses = {str(info[4][0]) for info in socket.getaddrinfo(host, None)}
    except socket.gaierror as exc:
        raise ValidationError("The web host could not be resolved.") from exc
    if not addresses or any(not _is_public_address(address) for address in addresses):
        raise ValidationError("Private and local web hosts are not allowed.")
    return url


class WebRetrievalService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def retrieve(self, url: str, *, opted_in: bool) -> list[Citation]:
        if not self._settings.web_retrieval_enabled or not opted_in:
            return []
        validate_web_url(url, self._settings.web_retrieval_allowlist)
        timeout = httpx.Timeout(self._settings.web_retrieval_timeout_seconds)
        async with (
            httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client,
            client.stream("GET", url) as response,
        ):
            response.raise_for_status()
            chunks: list[bytes] = []
            size = 0
            async for part in response.aiter_bytes():
                size += len(part)
                if size > self._settings.web_retrieval_max_bytes:
                    raise ValidationError("Web response exceeds the configured size limit.")
                chunks.append(part)
        body = b"".join(chunks).decode("utf-8", errors="replace")
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()
        return [
            Citation(
                document_id=url,
                title=urlparse(url).hostname or url,
                chunk_id="web:0",
                snippet=text[:500],
                locator=url,
                untrusted=True,
            )
        ]
