import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import Sector, UserMembership
from apps.meetings.models import Meeting


@pytest.mark.django_db
def test_only_active_staff_can_use_admin_api(api, user):
    assert api.get("/api/admin/sectors/").status_code == 403
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    assert api.get("/api/admin/sectors/").status_code == 200
    user.membership.sector.is_active = False
    user.membership.sector.save(update_fields=["is_active"])
    assert api.get("/api/admin/sectors/").status_code == 403


@pytest.mark.django_db
def test_admin_creates_sector_and_user_with_one_membership(api, user):
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    sector_response = api.post(
        "/api/admin/sectors/", {"name": "Pesquisa", "slug": "pesquisa"}, format="json"
    )
    assert sector_response.status_code == 201
    sector_id = sector_response.data["id"]
    response = api.post(
        "/api/admin/users/",
        {
            "username": "carla",
            "password": "Safe-Temporary-Password-789",
            "sector_id": sector_id,
            "email": "carla@example.org",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    assert "password" not in response.data
    created = get_user_model().objects.get(username="carla")
    assert created.check_password("Safe-Temporary-Password-789")
    assert UserMembership.objects.get(user=created).sector_id == sector_id
    assert len(api.get(f"/api/admin/sectors/{sector_id}/members/").data["results"]) == 1


@pytest.mark.django_db
def test_cannot_move_owner_across_sectors_or_deactivate_occupied_sector(api, user, other_user):
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    meeting = Meeting.objects.create(owner=other_user, title="Preservada")
    sector = Sector.objects.create(name="Outro", slug="outro")
    response = api.patch(
        f"/api/admin/users/{other_user.pk}/", {"sector_id": sector.pk}, format="json"
    )
    assert response.status_code == 400
    assert Meeting.objects.get(pk=meeting.pk).sector_id == other_user.membership.sector_id
    response = api.patch(
        f"/api/admin/sectors/{user.membership.sector_id}/",
        {"is_active": False}, format="json",
    )
    assert response.status_code == 400
