from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0007_sector_max_monthly_minutes_per_user")]

    operations = [
        migrations.AddField(
            model_name="usermembership",
            name="must_change_password",
            field=models.BooleanField(default=False),
        ),
    ]
