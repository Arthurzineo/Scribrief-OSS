from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from apps.accounts.services.ai_budget import tracked_openai_call
from apps.audit.models import AIUsageEvent
from apps.audit.usage import estimate_cost, record_openai_usage
from apps.meetings.models import Meeting


@pytest.mark.django_db
def test_usage_ledger_attributes_minutes_call_and_preserves_history(user):
    meeting = Meeting.objects.create(owner=user, title="Custo")
    job_id = uuid4()
    context = {
        "sector_id": meeting.sector_id, "user_id": user.pk,
        "meeting_id": meeting.pk, "job_id": job_id,
        "operation": "minutes", "key_version": 2,
    }
    response = SimpleNamespace(
        usage={"input_tokens": 100_000, "output_tokens": 10_000,
               "input_tokens_details": {"cached_tokens": 20_000}},
        _request_id="req-test-minutes-1",
    )
    record_openai_usage(response, context, "gpt-6-luna")
    event = AIUsageEvent.objects.get(request_id="req-test-minutes-1")
    assert event.estimated_usd == Decimal("0.01320000")
    assert event.estimate_status == "estimated"
    assert event.requested_by_id == user.pk and event.sector_id == meeting.sector_id
    assert event.meeting_id == meeting.pk and event.job_id == job_id
    assert event.key_version == 2 and event.operation == "minutes"
    meeting.delete()
    assert AIUsageEvent.objects.filter(pk=event.pk).exists()


def test_duration_only_diarization_usage_has_no_fabricated_cost():
    amount, status, version = estimate_cost(
        "gpt-4o-transcribe-diarize", {"type": "duration", "seconds": 1200}
    )
    assert amount is None and status == "unavailable" and not version


def test_luna_long_context_tier_is_not_undercounted():
    amount, status, version = estimate_cost(
        "gpt-6-luna", {"input_tokens": 300_000, "output_tokens": 10_000}
    )
    assert amount == Decimal("0.06750000")
    assert status == "estimated" and version


@pytest.mark.django_db
def test_admin_can_filter_costs_by_user_sector_and_meeting(api, user, other_user):
    meeting = Meeting.objects.create(owner=user, title="Custos por ata")
    context = {
        "sector_id": meeting.sector_id, "user_id": user.pk,
        "meeting_id": meeting.pk, "job_id": uuid4(),
        "operation": "minutes", "key_version": 1,
    }
    record_openai_usage(
        SimpleNamespace(usage={"input_tokens": 1000, "output_tokens": 100},
                        _request_id="req-report-1"),
        context, "gpt-6-luna",
    )
    api.force_authenticate(user=other_user)
    assert api.get("/api/admin/usage/").status_code == 403
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    api.force_authenticate(user=user)
    filters = {"user_id": user.pk, "sector_id": meeting.sector_id,
               "meeting_id": str(meeting.pk), "operation": "minutes"}
    summary = api.get("/api/admin/usage/summary/", filters)
    assert summary.status_code == 200
    assert summary.data["totals"]["calls"] == 1
    assert summary.data["totals"]["minutes_usd"] is not None
    report = api.get("/api/admin/usage/", filters).data
    assert report["count"] == 1
    assert report["results"][0]["usage_basis"] == "measured"
    assert report["results"][0]["estimate_status"] == "estimated"


@pytest.mark.django_db
def test_retry_records_failed_and_successful_attempt_without_secrets(user):
    meeting = Meeting.objects.create(owner=user, title="Retry")
    context = {
        "sector_id": meeting.sector_id, "user_id": user.pk,
        "meeting_id": meeting.pk, "job_id": uuid4(),
        "operation": "transcription", "key_version": 3,
    }
    class MockAPIError(RuntimeError):
        request_id = "req-failed-retry"

    def fail():
        raise MockAPIError("secret sk-NEVER-STORE and transcript")

    with pytest.raises(MockAPIError):
        tracked_openai_call(fail, context, "gpt-4o-transcribe-diarize", "chunk-7")
    response = SimpleNamespace(
        usage={"input_tokens": 2000, "output_tokens": 100},
        _request_id="req-success-retry",
    )
    tracked_openai_call(lambda: response, context, "gpt-4o-transcribe-diarize", "chunk-7")
    events = list(AIUsageEvent.objects.filter(meeting_id=meeting.pk).order_by("id"))
    assert len(events) == 2
    assert [event.outcome for event in events] == ["failed", "success"]
    assert events[0].estimated_usd is None
    assert events[1].estimated_usd == Decimal("0.00600000")
    assert "NEVER-STORE" not in str(events[0].__dict__)
    assert events[0].source_label == events[1].source_label == "chunk-7"


@pytest.mark.django_db
def test_usage_request_id_deduplicates_replayed_callback(user):
    meeting = Meeting.objects.create(owner=user, title="Duplicata")
    context = {
        "sector_id": meeting.sector_id, "user_id": user.pk,
        "meeting_id": meeting.pk, "job_id": uuid4(),
        "operation": "minutes", "key_version": 1,
    }
    response = SimpleNamespace(
        usage={"input_tokens": 100, "output_tokens": 50},
        _request_id="req-same-twice",
    )
    record_openai_usage(response, context, "gpt-6-luna")
    record_openai_usage(response, context, "gpt-6-luna")
    assert AIUsageEvent.objects.filter(request_id="req-same-twice").count() == 1


@pytest.mark.django_db
def test_transfer_does_not_reattribute_historical_cost(api, user, other_user):
    meeting = Meeting.objects.create(owner=user, title="Custo transferido", status="transcrito")
    context = {
        "sector_id": meeting.sector_id, "user_id": user.pk,
        "meeting_id": meeting.pk, "job_id": uuid4(),
        "operation": "minutes", "key_version": 1,
    }
    record_openai_usage(
        SimpleNamespace(
            usage={"input_tokens": 1000, "output_tokens": 100},
            _request_id="req-before-transfer",
        ), context, "gpt-6-luna",
    )
    response = api.post(
        f"/api/v1/meetings/{meeting.pk}/transfer/",
        {"target_user_id": other_user.pk, "access_version": 0}, format="json",
    )
    assert response.status_code == 200
    assert AIUsageEvent.objects.get(request_id="req-before-transfer").requested_by_id == user.pk
