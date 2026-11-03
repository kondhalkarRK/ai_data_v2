from app.core.config import Settings


def test_ssl_verify_can_be_disabled_for_local_self_signed_certificates() -> None:
    settings = Settings(ssl_verify=False)
    assert settings.ssl_verify is False
    assert settings.httpx_verify is False


def test_ssl_cert_file_is_supported_when_provider_uses_a_private_ca() -> None:
    settings = Settings(ssl_cert_file="/tmp/custom-ca.pem")
    assert settings.ssl_cert_file == "/tmp/custom-ca.pem"
    assert settings.httpx_verify == "/tmp/custom-ca.pem"
