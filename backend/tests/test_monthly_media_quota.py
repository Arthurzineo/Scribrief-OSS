from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction

from apps.meetings.models import Meeting, MonthlyMediaUsage, ProcessingJob
from apps.meetings.services.common import Conflict
from apps.meetings.services.media_quota import current_period, reserve_monthly_media


def test_brazil_calendar_month_boundary_and_year_rollover():
    assert current_period(datetime(2026, 10, 1, 2, 59, tzinfo=UTC)) == date(2026, 9, 1)
    assert current_period(datetime(2026, 10, 1, 3, 0, tzinfo=UTC)) == date(2026, 10, 1)
    assert current_period(datetime(2027, 1, 1, 2, 59, tzinfo=UTC)) == date(2026, 12, 1)


@pytest.mark.django_db
def test_quota_counts_accepted_uploads_and_resets_by_month(user, other_user):
    sector = user.membership.sector
    sector.max_monthly_minutes_per_user = 2
    sector.save(update_fields=["max_monthly_minutes_per_user"])
    meeting = SimpleNamespace(owner_id=user.pk, sector_id=sector.pk)
    other = SimpleNamespace(owner_id=other_user.pk, sector_id=sector.pk)
    with patch("apps.meetings.services.media_quota.current_period", return_value=date(2026, 10, 1)):
        with transaction.atomic():
            usage = reserve_monthly_media(meeting, 59.999)
        assert usage.used_seconds == Decimal("60.00")
        with transaction.atomic():
            reserve_monthly_media(meeting, 60)
        with pytest.raises(Conflict):
            with transaction.atomic():
                reserve_monthly_media(meeting, 0.01)
        with transaction.atomic():
            reserve_monthly_media(other, 60)
    assert (
        MonthlyMediaUsage.objects.get(
            sector=sector, user_id_snapshot=user.pk, period=date(2026, 10, 1)
        ).upload_count
        == 2
    )
    assert MonthlyMediaUsage.objects.filter(sector=sector, period=date(2026, 10, 1)).count() == 2
    with patch("apps.meetings.services.media_quota.current_period", return_value=date(2026, 11, 1)):
        with transaction.atomic():
            new = reserve_monthly_media(meeting, 120)
    assert new.period == date(2026, 11, 1) and new.used_seconds == Decimal("120.00")


@pytest.mark.django_db
def test_limit_can_be_enabled_after_usage_was_already_recorded(user):
    sector = user.membership.sector
    meeting = SimpleNamespace(owner_id=user.pk, sector_id=sector.pk)
    with transaction.atomic():
        reserve_monthly_media(meeting, 90)
    sector.max_monthly_minutes_per_user = 1
    sector.save(update_fields=["max_monthly_minutes_per_user"])
    with pytest.raises(Conflict):
        with transaction.atomic():
            reserve_monthly_media(meeting, 1)
    assert MonthlyMediaUsage.objects.get(user_id_snapshot=user.pk).used_seconds == 90


@pytest.mark.django_db
def test_admin_sets_monthly_limit_and_sees_member_usage(api, user, other_user):
    sector = user.membership.sector
    path = f"/api/admin/sectors/{sector.pk}/"
    assert api.patch(path, {"max_monthly_minutes_per_user": 10}, format="json").status_code == 403
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    assert api.patch(path, {"max_monthly_minutes_per_user": 0}, format="json").status_code == 400
    assert (
        api.patch(path, {"max_monthly_minutes_per_user": 44641}, format="json").status_code == 400
    )
    assert api.patch(path, {"max_monthly_minutes_per_user": 10}, format="json").status_code == 200
    with transaction.atomic():
        reserve_monthly_media(SimpleNamespace(owner_id=other_user.pk, sector_id=sector.pk), 125)
    response = api.get(f"/api/admin/sectors/{sector.pk}/members/")
    assert response.status_code == 200
    member = next(item for item in response.data["results"] if item["id"] == other_user.pk)
    assert member["monthly_used_seconds"] == "125.00"
    assert member["monthly_upload_count"] == 1
    assert response.data["monthly_period"] == current_period().strftime("%Y-%m")


@pytest.mark.django_db
def test_upload_reservation_blocks_second_file_without_job_or_media(api, user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    sector = user.membership.sector
    sector.max_monthly_minutes_per_user = 2
    sector.save(update_fields=["max_monthly_minutes_per_user"])
    first = Meeting.objects.create(owner=user, title="Primeiro")
    second = Meeting.objects.create(owner=user, title="Segundo")

    def upload(meeting):
        media = SimpleUploadedFile("clip.mp3", b"ID3" + b"x" * 100)
        return api.post(
            f"/api/v1/meetings/{meeting.pk}/upload/",
            {"file": media, "consent_confirmed": "true"},
            format="multipart",
        )

    with (
        patch("apps.meetings.storage.probe_audio"),
        patch("apps.meetings.views.processing.duration_seconds", return_value=70),
        patch("apps.meetings.transcription_jobs.enqueue_transcription"),
    ):
        assert upload(first).status_code == 202
        denied = upload(second)
        assert denied.status_code == 409
        assert "Cota mensal" in str(denied.data)
        assert upload(first).status_code == 409
    usage = MonthlyMediaUsage.objects.get(user_id_snapshot=user.pk)
    assert usage.used_seconds == Decimal("70.00") and usage.upload_count == 1
    assert ProcessingJob.objects.filter(meeting_id=second.pk).count() == 0
    assert not (tmp_path / "reunioes" / str(second.pk) / "original.mp3").exists()


@pytest.mark.django_db
def test_per_file_limit_is_independent_and_does_not_debit_month(api, user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    sector = user.membership.sector
    sector.max_upload_minutes = 1
    sector.max_monthly_minutes_per_user = 10
    sector.save(update_fields=["max_upload_minutes", "max_monthly_minutes_per_user"])
    meeting = Meeting.objects.create(owner=user, title="Longo")
    media = SimpleUploadedFile("clip.mp3", b"ID3" + b"x" * 100)
    with (
        patch("apps.meetings.storage.probe_audio"),
        patch("apps.meetings.processing.pipeline.duration_seconds", return_value=70),
    ):
        denied = api.post(
            f"/api/v1/meetings/{meeting.pk}/upload/",
            {"file": media, "consent_confirmed": "true"},
            format="multipart",
        )
    assert denied.status_code == 400
    assert MonthlyMediaUsage.objects.count() == 0
    assert ProcessingJob.objects.count() == 0
