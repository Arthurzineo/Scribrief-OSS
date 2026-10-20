from django.db import migrations, models


def mark_existing_bootstrap(apps, schema_editor):
    membership = apps.get_model("accounts", "UserMembership")
    membership.objects.filter(
        user__username="ADMIN", user__is_superuser=True, must_change_password=True,
    ).update(bootstrap_local_only=True)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0008_usermembership_must_change_password")]

    operations = [
        migrations.AddField(
            model_name="usermembership",
            name="bootstrap_local_only",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(mark_existing_bootstrap, migrations.RunPython.noop),
    ]
