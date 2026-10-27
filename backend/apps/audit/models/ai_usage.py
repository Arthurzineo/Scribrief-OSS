from django.conf import settings
from django.db import models


class AIUsageEvent(models.Model):
    """One external call, attributed at call time; survives meeting deletion."""

    sector = models.ForeignKey("accounts.Sector", on_delete=models.PROTECT)
    budget_entry = models.ForeignKey(
        "audit.AIBudgetEntry", null=True, on_delete=models.SET_NULL
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    meeting_id = models.UUIDField()
    job_id = models.UUIDField(null=True)
    operation = models.CharField(max_length=40)
    provider_id = models.CharField(max_length=40, default="openai")
    model = models.CharField(max_length=100)
    key_version = models.PositiveIntegerField()
    prompt_version = models.PositiveIntegerField(null=True)
    prompt_fingerprint = models.CharField(max_length=64, blank=True)
    request_id = models.CharField(max_length=100, blank=True)
    outcome = models.CharField(max_length=16, default="success")
    error_type = models.CharField(max_length=80, blank=True)
    source_label = models.CharField(max_length=100, blank=True)
    usage = models.JSONField(default=dict)
    input_tokens = models.PositiveBigIntegerField(null=True)
    output_tokens = models.PositiveBigIntegerField(null=True)
    total_tokens = models.PositiveBigIntegerField(null=True)
    estimated_usd = models.DecimalField(max_digits=14, decimal_places=8, null=True)
    estimate_status = models.CharField(max_length=20, default="unavailable")
    pricing_version = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["sector", "created_at"]),
            models.Index(fields=["requested_by", "created_at"]),
            models.Index(fields=["meeting_id", "created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["request_id"], condition=~models.Q(request_id=""),
                name="unique_openai_request_id",
            ),
        ]
