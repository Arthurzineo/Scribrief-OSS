from django.db import migrations
from django.db.models import F
from django.conf import settings


def backfill(apps, schema_editor):
    Sector = apps.get_model("accounts", "Sector")
    UserMembership = apps.get_model("accounts", "UserMembership")
    Meeting = apps.get_model("meetings", "Meeting")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    db = schema_editor.connection.alias
    legacy, _ = Sector.objects.using(db).get_or_create(
        slug="legado", defaults={"name": "Setor legado"}
    )
    for user_id in User.objects.using(db).values_list("id", flat=True).iterator():
        UserMembership.objects.using(db).get_or_create(
            user_id=user_id, defaults={"sector_id": legacy.id}
        )
    Meeting.objects.using(db).filter(sector__isnull=True).update(sector_id=legacy.id)
    Meeting.objects.using(db).filter(created_by__isnull=True).update(created_by_id=F("owner_id"))


class Migration(migrations.Migration):
    dependencies = [
        ("meetings", "0013_meeting_created_by_meeting_sector_and_more"),
        ("accounts", "0001_initial"),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
