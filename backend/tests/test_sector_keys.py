import pytest

from apps.accounts.models import Sector, SectorOpenAIKey
from apps.accounts.secrets import sector_api_key
from apps.audit.models import AuditEvent


@pytest.mark.django_db
def test_admin_key_is_encrypted_rotatable_and_never_returned(api, user):
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    sector = Sector.objects.create(name="Pesquisa", slug="pesquisa")
    url = f"/api/admin/sectors/{sector.pk}/openai-key/"
    assert api.get(url).data["configured"] is False
    first = "sk-test-secret-sector-one-123456789"
    response = api.post(
        url,
        {"api_key": first, "current_password": "Strong-Test-Password-123"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data == {"configured": True, "version": 1}
    ciphertext = SectorOpenAIKey.objects.get(sector=sector).ciphertext
    assert first not in ciphertext
    assert first not in str(api.get(url).data)
    assert sector_api_key(sector.pk) == first
    assert first not in str(list(AuditEvent.objects.values_list("details", flat=True)))
    second = "sk-test-secret-sector-two-123456789"
    rotated = api.post(
        url,
        {"api_key": second, "current_password": "Strong-Test-Password-123"},
        format="json",
    )
    assert rotated.data["version"] == 2
    assert sector_api_key(sector.pk) == second
    assert api.delete(url, {"current_password": "wrong"}, format="json").status_code == 403
    assert api.delete(
        url, {"current_password": "Strong-Test-Password-123"}, format="json"
    ).status_code == 204
    assert api.get(url).data["configured"] is False


@pytest.mark.django_db
def test_new_meeting_requires_sector_key_without_global_fallback(api, user, settings):
    settings.OPENAI_API_KEY = "sk-global-must-not-be-used"
    SectorOpenAIKey.objects.filter(sector=user.membership.sector).delete()
    response = api.post("/api/v1/meetings/", {"title": "Bloqueada"}, format="json")
    assert response.status_code == 409
