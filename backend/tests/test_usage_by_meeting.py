from decimal import Decimal

import pytest

from apps.audit.models import AIUsageEvent
from apps.meetings.models import Meeting


@pytest.mark.django_db
def test_admin_meeting_costs_sum_known_operations_and_flag_missing_prices(api, user, other_user):
    meeting = Meeting.objects.create(owner=user, title="Reunião com chunks")
    other = Meeting.objects.create(owner=other_user, title="Outra reunião")
    def event(meeting_id, operation, amount, outcome="success", source_label=""):
        AIUsageEvent.objects.create(
            sector_id=meeting.sector_id, requested_by=user, meeting_id=meeting_id,
            operation=operation, provider_id="openai", model="synthetic", key_version=1,
            estimated_usd=amount,
            estimate_status="estimated" if amount is not None else "unavailable",
            outcome=outcome, source_label=source_label,
        )
    event(meeting.id, "transcription_chunk", Decimal("0.10000000"), source_label="chunk-1")
    event(meeting.id, "transcription_chunk", None, source_label="chunk-2")
    event(meeting.id, "minutes", Decimal("0.05000000"))
    event(meeting.id, "mind_map", Decimal("0.02000000"))
    event(meeting.id, "correction", None, outcome="failed")
    event(other.id, "minutes", Decimal("0.30000000"))
    api.force_authenticate(user=other_user)
    assert api.get("/api/admin/usage/meetings/").status_code == 403
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    api.force_authenticate(user=user)
    response = api.get("/api/admin/usage/meetings/", {"meeting_id": str(meeting.id)})
    assert response.status_code == 200
    assert response.data["count"] == 1
    row = response.data["results"][0]
    assert row["meeting_id"] == str(meeting.id)
    assert row["title"] == "Reunião com chunks"
    assert row["estimated_usd"] == Decimal("0.17000000")
    assert row["calls"] == 5 and row["unpriced_calls"] == 2
    assert row["failed_calls"] == 1
    by_operation = {entry["operation"]: entry for entry in row["operations"]}
    assert by_operation["transcription_chunk"]["calls"] == 2
    assert by_operation["transcription_chunk"]["unpriced_calls"] == 1
    assert by_operation["transcription_chunk"]["estimated_usd"] == Decimal("0.10000000")
    assert by_operation["minutes"]["estimated_usd"] == Decimal("0.05000000")
    assert by_operation["mind_map"]["estimated_usd"] == Decimal("0.02000000")
    assert by_operation["correction"]["estimated_usd"] is None
    assert api.get("/api/admin/usage/meetings/", {"meeting_id": "invalid"}).status_code == 400


@pytest.mark.django_db
def test_cost_history_retains_id_when_meeting_removed(api, user):
    meeting = Meeting.objects.create(owner=user, title="Removida")
    meeting_id = meeting.id
    AIUsageEvent.objects.create(
        sector=meeting.sector, requested_by=user, meeting_id=meeting_id,
        operation="minutes", provider_id="openai", model="synthetic", key_version=1,
        estimated_usd=Decimal("0.01000000"), estimate_status="estimated",
    )
    meeting.delete()
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    api.force_authenticate(user=user)
    row = api.get("/api/admin/usage/meetings/").data["results"][0]
    assert row["meeting_id"] == str(meeting_id)
    assert row["title"] is None
