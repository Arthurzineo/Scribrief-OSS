from django.db import models


class SectorAIPrompt(models.Model):
    sector = models.ForeignKey(
        "accounts.Sector", on_delete=models.CASCADE, related_name="ai_prompts"
    )
    kind = models.CharField(max_length=20)
    text = models.TextField()
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["sector", "kind"], name="unique_sector_ai_prompt")
        ]
