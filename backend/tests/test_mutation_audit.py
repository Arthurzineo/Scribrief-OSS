import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.meetings.models import Meeting


@pytest.mark.django_db
def test_mutations_are_audited_without_body_or_query(api, user):
    meeting = Meeting.objects.create(owner=user, title="Anterior")
    path = f"/api/v1/meetings/{meeting.id}/"
    response = api.patch(
        path + "?unused=should-not-be-recorded",
        {"title": "Nome confidencial"}, format="json", REMOTE_ADDR="203.0.113.66",
    )
    assert response.status_code == 200
    event = AuditEvent.objects.get(action="api_mutation", outcome="success")
    assert event.actor == user
    assert event.client_ip == "203.0.113.66"
    assert event.target_ref == path
    assert event.details == {"method": "PATCH", "status": 200}
    assert "Nome confidencial" not in str(event.details)
    assert "unused" not in event.target_ref


@pytest.mark.django_db
def test_audit_export_admin_only_filtered_and_no_request_body(api, user, other_user):
    meeting = Meeting.objects.create(owner=user, title="Segredo da reunião")
    api.patch(
        f"/api/v1/meetings/{meeting.pk}/", {"title": "segredo no corpo"},
        format="json", REMOTE_ADDR="203.0.113.66",
    )
    api.force_authenticate(user=other_user)
    assert api.get("/api/admin/audit/export/").status_code == 403
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    api.force_authenticate(user=user)
    assert api.get("/api/admin/audit/", {"from_date": "bad"}).status_code == 400
    response = api.get("/api/admin/audit/export/", {"action": "api_mutation"})
    assert response.status_code == 200
    assert "attachment" in response["Content-Disposition"]
    rows = [json.loads(line) for line in response.streaming_content]
    assert len(rows) == 1
    assert rows[0]["client_ip"] == "203.0.113.66"
    assert "segredo no corpo" not in str(rows)
    assert AuditEvent.objects.filter(action="audit_export", actor=user).count() == 1


@pytest.mark.django_db
def test_retention_is_dry_run_by_default_and_minimum_90_days(user):
    event = AuditEvent.objects.create(actor=user, action="old", outcome="success")
    AuditEvent.objects.filter(pk=event.pk).update(
        created_at=timezone.now() - timedelta(days=200)
    )
    cutoff = (timezone.localdate() - timedelta(days=180)).isoformat()
    output = StringIO()
    call_command("prune_audit", before=cutoff, stdout=output)
    assert "DRY RUN: 1" in output.getvalue()
    assert AuditEvent.objects.filter(pk=event.pk).exists()
    with pytest.raises(CommandError):
        call_command("prune_audit", before=timezone.localdate().isoformat())
    call_command("prune_audit", before=cutoff, confirm=True, stdout=StringIO())
    assert not AuditEvent.objects.filter(pk=event.pk).exists()
    assert AuditEvent.objects.filter(action="audit_retention_purge").count() == 1
