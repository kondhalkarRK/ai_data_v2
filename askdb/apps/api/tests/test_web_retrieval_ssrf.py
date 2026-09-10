"""SSRF validation rejects local targets before HTTP is attempted."""

import socket

import pytest

from app.core.exceptions import ValidationError
from app.services.web_retrieval import validate_web_url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://10.0.0.8/secrets",
        "http://169.254.169.254/latest/meta-data",
        "http://localhost:8000",
    ],
)
def test_private_hosts_are_rejected(url: str) -> None:
    host = url.split("//", 1)[1].split("/", 1)[0].split(":", 1)[0]
    with pytest.raises(ValidationError):
        validate_web_url(url, [host])


def test_dns_rebinding_to_private_address_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.2", 0))
        ],
    )
    with pytest.raises(ValidationError):
        validate_web_url("https://docs.example.com/page", ["example.com"])
