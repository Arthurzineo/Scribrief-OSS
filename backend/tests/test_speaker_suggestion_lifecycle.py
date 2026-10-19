from unittest.mock import patch

import pytest

from apps.meetings.models import Meeting, MeetingStatus, Segment, Speaker


@pytest.fixture
def speaker_meeting(user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Vozes", status=MeetingStatus.TRANSCRITO,
        transcription_version=1, audio_path="audio.mp3",
    )
    (tmp_path / "audio.mp3").write_bytes(b"mp3")
    for index, code in enumerate(("A", "B", "C")):
        speaker = Speaker.objects.create(meeting=meeting, code=code, name=code)
        Segment.objects.create(
            meeting=meeting, speaker=speaker, start_ms=index * 10000,
            end_ms=index * 10000 + 3000, text="Fala", order=index,
        )
    return meeting


@pytest.mark.django_db
def test_analysis_persists_and_two_requests_is_hard_limit(api, speaker_meeting):
    path = f"/api/v1/meetings/{speaker_meeting.id}/speaker-suggestions/"
    with patch("apps.meetings.tasks.analyze_speaker_reconciliation.delay") as enqueue:
        assert api.get(path).data["remaining"] == 2
        first = api.post(path, {"version": 1}, format="json")
        assert first.status_code == 202
        assert first.data["remaining"] == 1
        assert api.post(path, {"version": 1}, format="json").data["job_id"] == first.data["job_id"]
        assert api.get(path).data["status"] == "processing"
        assert api.get(path).data["job_id"] == first.data["job_id"]
        enqueue.assert_called_once()
        dismissed = api.post(f"{path}dismiss/", {"version": 1}, format="json")
        assert dismissed.status_code == 409  # No dismissal while still processing.
        from apps.meetings.models import SpeakerAnalysis

        analysis = SpeakerAnalysis.objects.get(meeting=speaker_meeting)
        analysis.status = "ready"
        analysis.groups = [["A", "B"], ["B", "C"]]
        analysis.save(update_fields=["status", "groups"])
        assert api.get(path).data["groups"] == [["A", "B"], ["B", "C"]]
        dismissed_group = api.post(
            f"{path}dismiss/", {"version": 1, "codes": ["A", "B"]}, format="json"
        )
        assert dismissed_group.data["groups"] == [["B", "C"]]
        assert api.get(path).data["groups"] == [["B", "C"]]
        dismissed_all = api.post(f"{path}dismiss/", {"version": 1}, format="json")
        assert dismissed_all.data["status"] == "dismissed"
        second = api.post(path, {"version": 1}, format="json")
        assert second.status_code == 202
        assert second.data["remaining"] == 0
        assert second.data["job_id"] != first.data["job_id"]
        assert api.post(path, {"version": 1}, format="json").data["job_id"] == second.data["job_id"]
        assert enqueue.call_count == 2
        analysis.refresh_from_db()
        analysis.status = "ready"
        analysis.groups = []
        analysis.save(update_fields=["status", "groups"])
        assert api.post(path, {"version": 1}, format="json").status_code == 409


@pytest.mark.django_db
def test_analysis_is_owner_scoped_and_queue_failure_does_not_consume_use(
    api, user, other_user, speaker_meeting
):
    path = f"/api/v1/meetings/{speaker_meeting.id}/speaker-suggestions/"
    with patch(
        "apps.meetings.tasks.analyze_speaker_reconciliation.delay",
        side_effect=RuntimeError,
    ):
        assert api.post(path, {"version": 1}, format="json").status_code == 503
    assert api.get(path).data["remaining"] == 2
    api.force_authenticate(user=other_user)
    assert api.get(path).status_code == 404
    assert api.post(f"{path}dismiss/", {"version": 1}, format="json").status_code == 404
    api.force_authenticate(user=user)
