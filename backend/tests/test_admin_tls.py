"""TLS bootstrap and rotation must fail closed without persisting keys in the DB."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.admin_panel import tls_service
from apps.admin_panel.views import tls as tls_view
from apps.audit.models import AuditEvent


def test_self_signed_san_and_atomic_pair(tmp_path, monkeypatch):
    names = ("scribrief.interno", "127.0.0.1")
    monkeypatch.setattr(tls_service, "hostnames", lambda: names)
    cert, key = tls_service.generate_self_signed(names)
    details = tls_service.install_pair(cert, key, names, tmp_path)
    assert len(details["fingerprint_sha256"]) == 64
    assert details["self_issued"] is True
    original = (tmp_path / "current.pem").read_bytes()
    assert tls_service.current_status(tmp_path)["valid"] is True
    # A supplied full chain must not make the administrative status fail.
    tls_service.install_pair(cert + cert, key, names, tmp_path)
    assert tls_service.current_status(tmp_path)["valid"] is True
    original = (tmp_path / "current.pem").read_bytes()
    malformed_chain = cert + b"-----BEGIN CERTIFICATE-----\nbad\n-----END CERTIFICATE-----\n"
    with pytest.raises(ValueError):
        tls_service.install_pair(malformed_chain, key, names, tmp_path)
    assert (tmp_path / "current.pem").read_bytes() == original
    other_cert, other_key = tls_service.generate_self_signed(names)
    with pytest.raises(ValueError, match="não corresponde"):
        tls_service.install_pair(other_cert, key, names, tmp_path)
    assert (tmp_path / "current.pem").read_bytes() == original
    with pytest.raises(ValueError, match="SAN"):
        tls_service.install_pair(other_cert, other_key, ("outro.interno",), tmp_path)
    assert (tmp_path / "current.pem").read_bytes() == original


@pytest.mark.django_db
def test_admin_tls_requires_staff_password_and_never_returns_key(api, user, tmp_path, monkeypatch):
    monkeypatch.setattr(tls_view, "TLS_ROOT", tmp_path)
    monkeypatch.setattr(tls_service, "TLS_ROOT", tmp_path)
    monkeypatch.setattr(tls_service, "hostnames", lambda: ("127.0.0.1",))
    monkeypatch.setattr(tls_view, "hostnames", lambda: ("127.0.0.1",))
    url = "/api/admin/tls/"
    assert api.get(url).status_code == 403
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    cert, key = tls_service.generate_self_signed(("127.0.0.1",))

    def payload(password, key_bytes=key):
        return {
            "certificate": SimpleUploadedFile(
                "cert.pem", cert, content_type="application/x-pem-file"
            ),
            "private_key": SimpleUploadedFile(
                "key.pem", key_bytes, content_type="application/x-pem-file"
            ),
            "current_password": password,
        }

    assert api.post(url, payload("wrong"), format="multipart").status_code == 403
    assert not (tmp_path / "current.pem").exists()
    assert (
        api.post(
            url, payload("Strong-Test-Password-123", b"not a key"), format="multipart"
        ).status_code
        == 400
    )
    assert not (tmp_path / "current.pem").exists()
    result = api.post(url, payload("Strong-Test-Password-123"), format="multipart")
    assert result.status_code == 200
    assert result.data["activation"] == "pending_reload"
    assert b"PRIVATE KEY" in (tmp_path / "current.pem").read_bytes()
    assert "PRIVATE KEY" not in str(result.data)
    assert "PRIVATE KEY" not in str(api.get(url).data)
    assert "PRIVATE KEY" not in str(list(AuditEvent.objects.values_list("details", flat=True)))
    assert (
        AuditEvent.objects.filter(action="tls_certificate_rotation", outcome="success").count() == 1
    )
    assert AuditEvent.objects.filter(action="tls_certificate_rotation_requested").count() == 1
