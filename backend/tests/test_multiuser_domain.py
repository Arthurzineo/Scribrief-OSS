import pytest
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError

from apps.accounts.models import Sector, UserMembership
from apps.accounts.secrets import save_sector_key
from apps.meetings.models import Meeting


@pytest.mark.django_db
def test_membership_and_admin_contract_have_no_external_auth_scaffolding(api, user):
    fields = {field.name for field in UserMembership._meta.fields}
    assert "auth_source" not in fields
    assert "external_id" not in fields
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    response = api.get("/api/admin/users/")
    assert response.status_code == 200
    assert "auth_source" not in response.data["results"][0]


@pytest.mark.django_db
def test_member_has_one_sector_and_meeting_snapshots_creator_and_sector(api, user):
    sector = Sector.objects.create(name="Ensino", slug="ensino")
    save_sector_key(sector, "sk-test-ensino-not-real-123456")
    user.membership.sector = sector
    user.membership.save(update_fields=["sector"])
    response = api.post("/api/v1/meetings/", {"title": "Planejamento"}, format="json")
    assert response.status_code == 201
    meeting = Meeting.objects.get(pk=response.data["id"])
    assert meeting.owner == user
    assert meeting.created_by == user
    assert meeting.sector == sector
    assert isinstance(meeting.audio_path, str)


@pytest.mark.django_db
def test_meeting_owner_cannot_be_deleted_with_history(user):
    sector = user.membership.sector
    meeting = Meeting.objects.create(
        owner=user, created_by=user, sector=sector, title="Histórico"
    )
    with pytest.raises(ProtectedError):
        user.delete()
    assert Meeting.objects.filter(pk=meeting.pk).exists()


@pytest.mark.django_db
def test_meeting_cannot_be_created_in_another_sector(user):
    other_sector = Sector.objects.create(name="Saúde", slug="saude")
    with pytest.raises(ValidationError):
        Meeting.objects.create(owner=user, sector=other_sector, title="Fora do setor")
    assert not Meeting.objects.filter(title="Fora do setor").exists()


@pytest.mark.django_db
def test_member_without_active_sector_cannot_create_or_list(api, user):
    user.membership.sector.is_active = False
    user.membership.sector.save(update_fields=["is_active"])
    response = api.post("/api/v1/meetings/", {"title": "Bloqueada"}, format="json")
    assert response.status_code == 400
    assert api.get("/api/v1/meetings/").data["results"] == []


@pytest.mark.django_db
def test_local_login_and_session_keep_meeting_access(client, user):
    meeting = Meeting.objects.create(owner=user, title="Privada")
    response = client.post(
        "/api/v1/login/",
        data='{"username":"ana","password":"Strong-Test-Password-123"}',
        content_type="application/json",
    )
    assert response.status_code == 200
    assert client.get(f"/api/v1/meetings/{meeting.id}/").status_code == 200


@pytest.mark.django_db
def test_sector_and_staff_do_not_bypass_owner_policy(api, user, other_user):
    meeting = Meeting.objects.create(owner=other_user, title="Sem partilha")
    detail = f"/api/v1/meetings/{meeting.id}/"
    assert api.get(detail).status_code == 404
    assert api.get(f"{detail}audio/").status_code == 404
    assert api.get(f"{detail}progress/").status_code == 404
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    assert api.get(detail).status_code == 404
    different = Sector.objects.create(name="Outro", slug="outro")
    other_user.membership.sector = different
    other_user.membership.save(update_fields=["sector"])
    assert api.get(detail).status_code == 404
