from django.db import models

from .sector import Sector


class SectorAICredential(models.Model):
    """Encrypted credential scoped to one sector and one reviewed provider."""

    sector = models.ForeignKey(
        Sector, on_delete=models.CASCADE, related_name="ai_credentials"
    )
    provider_id = models.CharField(max_length=40, default="openai")
    ciphertext = models.TextField()
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["sector", "provider_id"], name="unique_sector_ai_provider_credential"
        )]
