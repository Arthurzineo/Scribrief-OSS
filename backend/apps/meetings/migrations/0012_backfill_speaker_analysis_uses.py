from django.db import migrations
from django.db.models import Count


def backfill_uses(apps, schema_editor):
    AuditEvent = apps.get_model("audit", "AuditEvent")
    Meeting = apps.get_model("meetings", "Meeting")
    SpeakerAnalysis = apps.get_model("meetings", "SpeakerAnalysis")
    database = schema_editor.connection.alias
    usage = (
        AuditEvent.objects.using(database)
        .filter(action="speaker_reconciliation_requested", outcome="success")
        .exclude(target_id__isnull=True)
        .values("target_id")
        .annotate(total=Count("id"))
    )
    for item in usage.iterator():
        meeting = Meeting.objects.using(database).filter(pk=item["target_id"]).first()
        if meeting is not None:
            SpeakerAnalysis.objects.using(database).get_or_create(
                meeting_id=meeting.id,
                defaults={"uses": min(item["total"], 2), "version": meeting.transcription_version},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("meetings", "0011_speakeranalysis"),
        ("audit", "0001_initial"),
    ]

    operations = [migrations.RunPython(backfill_uses, migrations.RunPython.noop)]
