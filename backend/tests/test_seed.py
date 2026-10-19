import pytest
from django.core.management import call_command

from apps.meetings.models import Meeting, MeetingStatus


@pytest.mark.django_db
def test_seed_is_explicit_and_idempotent(settings, tmp_path, monkeypatch):
    settings.MEDIA_ROOT = tmp_path
    monkeypatch.setenv("DEMO_SEED_ALLOWED", "true")
    monkeypatch.setenv("DEMO_PASSWORD", "Demo-Test-Password-123")
    call_command("seed_demo")
    call_command("seed_demo")
    meeting = Meeting.objects.get(title="DEMO — reunião de exemplo")
    assert Meeting.objects.count() == 1
    assert meeting.status == MeetingStatus.ATA_PRONTA
    assert meeting.segments.count() == 2
    assert (tmp_path / "reunioes" / str(meeting.id) / "ata.json").exists()


@pytest.mark.django_db
def test_seed_requires_explicit_approval(monkeypatch):
    monkeypatch.delenv("DEMO_SEED_ALLOWED", raising=False)
    monkeypatch.setenv("DEMO_PASSWORD", "Demo-Test-Password-123")
    with pytest.raises(Exception, match="DEMO_SEED_ALLOWED"):
        call_command("seed_demo")
