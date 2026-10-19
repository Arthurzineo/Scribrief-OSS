from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("meetings", "0022_monthlymediausage")]

    operations = [
        migrations.AddField(
            model_name="meeting",
            name="staged_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
