from datetime import UTC
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.accounts.services.ai_budget import (
    AIBudgetExceeded,
    budget_snapshot,
    current_period,
    reserve_ai_call,
    settle_ai_call,
    tracked_openai_call,
)
from apps.audit.models import AIBudgetEntry, AIUsageEvent, AuditEvent, SystemEvent
from apps.meetings.models import Meeting


def context(meeting, user, operation="minutes"):
    return {
        "sector_id": meeting.sector_id, "user_id": user.pk,
        "meeting_id": meeting.pk, "operation": operation, "key_version": 1,
    }


def response(request_id, input_tokens=1000, output_tokens=100):
    return SimpleNamespace(
        usage={"input_tokens": input_tokens, "output_tokens": output_tokens},
        _request_id=request_id,
    )


@pytest.mark.django_db
def test_user_budget_blocks_provider_before_another_call(user):
    meeting = Meeting.objects.create(owner=user, title="Orçamento pessoal")
    user.membership.monthly_ai_budget_usd = Decimal("0.05")
    user.membership.save(update_fields=["monthly_ai_budget_usd"])
    tracked_openai_call(
        lambda: response("budget-user-1"), context(meeting, user), "gpt-6-luna",
        reservation_usd=Decimal("0.04"),
    )
    called = []
    with pytest.raises(AIBudgetExceeded):
        tracked_openai_call(
            lambda: called.append(True), context(meeting, user), "gpt-6-luna",
            reservation_usd=Decimal("0.05"),
        )
    assert not called
    assert SystemEvent.objects.filter(
        event_code="ai_budget_denied", error_code="user_monthly_budget"
    ).exists()
    assert AIBudgetEntry.objects.filter(meeting_id=meeting.pk).count() == 1
    assert AIUsageEvent.objects.filter(meeting_id=meeting.pk).count() == 1


@pytest.mark.django_db
def test_sector_budget_is_shared_by_users_and_unpriced_call_keeps_reservation(
    user, other_user
):
    sector = user.membership.sector
    sector.monthly_ai_budget_usd = Decimal("0.05")
    sector.save(update_fields=["monthly_ai_budget_usd"])
    first = Meeting.objects.create(owner=user, title="Conta A")
    second = Meeting.objects.create(owner=other_user, title="Conta B")
    tracked_openai_call(
        lambda: SimpleNamespace(usage={"type": "duration", "seconds": 60},
                                _request_id="budget-unpriced-1"),
        context(first, user, "transcription_chunk"), "gpt-4o-transcribe-diarize",
        reservation_usd=Decimal("0.04"),
    )
    with pytest.raises(AIBudgetExceeded):
        tracked_openai_call(
            lambda: response("budget-sector-2"), context(second, other_user),
            "gpt-6-luna", reservation_usd=Decimal("0.02"),
        )
    entry = AIBudgetEntry.objects.get(meeting_id=first.pk)
    assert entry.status == "unpriced" and entry.charged_usd == Decimal("0.04")
    assert AIUsageEvent.objects.get(meeting_id=first.pk).estimated_usd is None


@pytest.mark.django_db
def test_budget_pool_counts_older_unlinked_usage_and_attributes_meeting(user):
    meeting = Meeting.objects.create(owner=user, title="Histórico")
    AIUsageEvent.objects.create(
        sector=meeting.sector, requested_by=user, meeting_id=meeting.pk,
        operation="transcription_chunk", model="gpt-4o-transcribe-diarize",
        key_version=1, estimated_usd=Decimal("0.08"),
    )
    user.membership.monthly_ai_budget_usd = Decimal("0.10")
    user.membership.save(update_fields=["monthly_ai_budget_usd"])
    with pytest.raises(AIBudgetExceeded):
        tracked_openai_call(
            lambda: response("budget-legacy"), context(meeting, user),
            "gpt-6-luna", reservation_usd=Decimal("0.03"),
        )


@pytest.mark.django_db
def test_staff_configures_sector_and_personal_budget_with_audit(api, user, other_user):
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    api.force_authenticate(user=user)
    sector = user.membership.sector
    saved = api.patch(
        f"/api/admin/sectors/{sector.pk}/",
        {"monthly_ai_budget_usd": "10.50"}, format="json",
    )
    assert saved.status_code == 200
    assert saved.data["monthly_ai_budget_usd"] == "10.50"
    member = api.patch(
        f"/api/admin/users/{other_user.pk}/",
        {"monthly_ai_budget_usd": "2.25"}, format="json",
    )
    assert member.status_code == 200
    assert member.data["monthly_ai_budget_usd"] == "2.25"
    budget_status = api.get(
        "/api/admin/usage/budget/",
        {"sector_id": sector.pk, "user_id": other_user.pk},
    )
    assert budget_status.status_code == 200
    assert budget_status.data["sector_limit_usd"] == "10.50"
    assert budget_status.data["user_limit_usd"] == "2.25"
    assert budget_status.data["sector_used_usd"] == "0.00000000"
    assert AuditEvent.objects.filter(action="sector_updated", target_ref=str(sector.pk)).exists()
    assert AuditEvent.objects.filter(action="user_updated", target_ref=str(other_user.pk)).exists()
    assert api.patch(
        f"/api/admin/sectors/{sector.pk}/",
        {"monthly_ai_budget_usd": "0"}, format="json",
    ).status_code == 400
    assert api.patch(
        f"/api/admin/users/{other_user.pk}/",
        {"monthly_ai_budget_usd": "-1"}, format="json",
    ).status_code == 400


@pytest.mark.django_db
def test_nonstaff_cannot_view_budget(api, other_user):
    api.force_authenticate(user=other_user)
    assert api.get(
        "/api/admin/usage/budget/", {"sector_id": other_user.membership.sector_id}
    ).status_code == 403


@pytest.mark.django_db
def test_meeting_cost_report_includes_local_budget_reservations(api, user):
    meeting = Meeting.objects.create(owner=user, title="Custos por reunião")
    tracked_openai_call(
        lambda: response("budget-meeting-1"), context(meeting, user), "gpt-6-luna",
        reservation_usd=Decimal("0.10"),
    )
    tracked_openai_call(
        lambda: SimpleNamespace(usage={"type": "duration", "seconds": 60},
                                _request_id="budget-meeting-2"),
        context(meeting, user, "transcription_chunk"), "gpt-4o-transcribe-diarize",
        reservation_usd=Decimal("0.20"),
    )
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    api.force_authenticate(user=user)
    report = api.get("/api/admin/usage/meetings/", {"meeting_id": str(meeting.pk)})
    assert report.status_code == 200
    row = report.data["results"][0]
    assert row["calls"] == 2 and row["unpriced_calls"] == 1
    assert row["budget_unpriced_calls"] == 1
    assert row["local_budget_usd"] > row["estimated_usd"]
    assert {item["operation"] for item in row["operations"]} == {
        "minutes", "transcription_chunk",
    }


@pytest.mark.django_db
def test_reservation_settles_once_and_denies_invalid_money(user):
    meeting = Meeting.objects.create(owner=user, title="Reserva")
    for invalid in (0, -1, "NaN", "Infinity", "0.000000001"):
        with pytest.raises(ValueError):
            reserve_ai_call(context(meeting, user), invalid)
    entry = reserve_ai_call(context(meeting, user), Decimal("0.20"))
    with pytest.raises(ValueError):
        settle_ai_call(entry, Decimal("-1"))
    settle_ai_call(entry, Decimal("0.05"))
    settle_ai_call(entry, Decimal("0.99"))
    assert budget_snapshot(meeting.sector_id, user.pk)["user_used_usd"] == Decimal("0.05")


@pytest.mark.django_db
def test_failed_provider_keeps_reservation_and_records_only_error_type(user):
    meeting = Meeting.objects.create(owner=user, title="Falha externa")

    def fail():
        raise RuntimeError("PRIVATE-PAYLOAD")

    with pytest.raises(RuntimeError):
        tracked_openai_call(fail, context(meeting, user), "gpt-6-luna",
                            reservation_usd=Decimal("0.40"))
    assert budget_snapshot(meeting.sector_id, user.pk)["user_used_usd"] == Decimal("0.40")
    assert AIBudgetEntry.objects.get().status == "unpriced"
    event = AIUsageEvent.objects.get()
    assert event.error_type == "RuntimeError" and "PRIVATE-PAYLOAD" not in str(event.__dict__)


@pytest.mark.django_db
def test_unsettled_crash_reservation_survives_meeting_deletion(user):
    meeting = Meeting.objects.create(owner=user, title="Interrompida")
    reserve_ai_call(context(meeting, user), Decimal("0.25"))
    meeting.delete()
    assert budget_snapshot(user.membership.sector_id, user.pk)["user_used_usd"] == Decimal("0.25")


def test_budget_month_uses_installation_timezone():
    from datetime import date, datetime

    assert current_period(datetime(2026, 11, 1, 1, tzinfo=UTC)) == date(2026, 10, 1)
    assert current_period(datetime(2026, 11, 1, 4, tzinfo=UTC)) == date(2026, 11, 1)


@pytest.mark.django_db
def test_new_month_does_not_reuse_previous_period_usage(user):
    from datetime import date

    meeting = Meeting.objects.create(owner=user, title="Outro mês")
    entry = reserve_ai_call(context(meeting, user), Decimal("0.25"))
    AIBudgetEntry.objects.filter(pk=entry.pk).update(period=date(2000, 1, 1))
    assert budget_snapshot(meeting.sector_id, user.pk)["user_used_usd"] == 0


@pytest.mark.django_db
def test_meeting_local_budget_obeys_operation_filter(api, user):
    meeting = Meeting.objects.create(owner=user, title="Filtro")
    for operation, value in (("minutes", "0.20"), ("mind_map", "0.30")):
        tracked_openai_call(
            lambda: SimpleNamespace(usage={}), context(meeting, user, operation),
            "gpt-6-luna", reservation_usd=Decimal(value),
        )
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    api.force_authenticate(user=user)
    data = api.get("/api/admin/usage/meetings/", {"operation": "minutes"}).data
    assert data["results"][0]["local_budget_usd"] == Decimal("0.20")


@pytest.mark.django_db
def test_exhausted_personal_budget_rejects_regeneration_before_enqueue(api, user):
    from unittest.mock import patch

    meeting = Meeting.objects.create(owner=user, title="Esgotado", status="transcrito")
    user.membership.monthly_ai_budget_usd = Decimal("0.10")
    user.membership.save(update_fields=["monthly_ai_budget_usd"])
    reserve_ai_call(context(meeting, user), Decimal("0.10"))
    with patch("apps.meetings.tasks.generate_minutes.delay") as enqueue:
        result = api.post(f"/api/v1/meetings/{meeting.pk}/minutes/")
    assert result.status_code == 409
    enqueue.assert_not_called()
    meeting.refresh_from_db()
    assert meeting.status == "transcrito" and meeting.job_id is None


@pytest.mark.django_db
@pytest.mark.parametrize(("sector_cap", "user_cap", "denied_scope"), [
    (None, None, None), ("0.01", None, "sector"), (None, "0.01", "user"),
])
def test_unlimited_scope_keeps_tracking_and_does_not_bypass_other_cap(
    user, sector_cap, user_cap, denied_scope,
):
    sector = user.membership.sector
    sector.monthly_ai_budget_usd = sector_cap
    sector.save(update_fields=["monthly_ai_budget_usd"])
    user.membership.monthly_ai_budget_usd = user_cap
    user.membership.save(update_fields=["monthly_ai_budget_usd"])
    meeting = Meeting.objects.create(owner=user, title="Sem teto opcional")
    def call():
        return response("unlimited-scope-test")

    if denied_scope:
        with pytest.raises(AIBudgetExceeded) as error:
            tracked_openai_call(call, context(meeting, user), "gpt-6-luna",
                                reservation_usd=Decimal("0.02"))
        assert error.value.scope == denied_scope
        assert not AIUsageEvent.objects.exists()
    else:
        tracked_openai_call(call, context(meeting, user), "gpt-6-luna",
                            reservation_usd=Decimal("50.00"))
        assert AIUsageEvent.objects.get().estimated_usd > 0
        assert budget_snapshot(sector.pk, user.pk)["user_used_usd"] > 0


@pytest.mark.django_db
def test_staff_can_remove_existing_caps_without_erasing_costs(api, user, other_user):
    sector = user.membership.sector
    sector.monthly_ai_budget_usd = Decimal("1")
    sector.save(update_fields=["monthly_ai_budget_usd"])
    other_user.membership.monthly_ai_budget_usd = Decimal("0.50")
    other_user.membership.save(update_fields=["monthly_ai_budget_usd"])
    meeting = Meeting.objects.create(owner=other_user, title="Remover teto")
    tracked_openai_call(lambda: response("before-unlimited"), context(meeting, other_user),
                        "gpt-6-luna", reservation_usd=Decimal("0.10"))
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    assert api.patch(f"/api/admin/sectors/{sector.pk}/", {
        "monthly_ai_budget_usd": None,
    }, format="json").status_code == 200
    assert api.patch(f"/api/admin/users/{other_user.pk}/", {
        "monthly_ai_budget_usd": None,
    }, format="json").status_code == 200
    snapshot = budget_snapshot(sector.pk, other_user.pk)
    assert snapshot["sector_limit_usd"] is snapshot["user_limit_usd"] is None
    assert snapshot["user_used_usd"] > 0 and AIUsageEvent.objects.count() == 1
