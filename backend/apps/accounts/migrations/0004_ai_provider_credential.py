from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('accounts', '0003_usermembership_session_version')]

    operations = [
        migrations.RenameModel(old_name='SectorOpenAIKey', new_name='SectorAICredential'),
        migrations.AlterField(
            model_name='sectoraicredential', name='sector',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, related_name='ai_credentials',
                to='accounts.sector',
            ),
        ),
        migrations.AddField(
            model_name='sectoraicredential', name='provider_id',
            field=models.CharField(default='openai', max_length=40),
        ),
        migrations.AddConstraint(
            model_name='sectoraicredential',
            constraint=models.UniqueConstraint(
                fields=('sector', 'provider_id'), name='unique_sector_ai_provider_credential',
            ),
        ),
    ]
