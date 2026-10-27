"""Durable local budget reservation for one external AI request."""

import uuid

from django.conf import settings
from django.db import models


class AIBudgetEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sector = models.ForeignKey("accounts.Sector", on_delete=models.PROTECT)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    user_id_snapshot = models.PositiveBigIntegerField()
    meeting_id = models.UUIDField()
    job_id = models.UUIDField(null=True)
    period = models.DateField()
    operation = models.CharField(max_length=40)
    reserved_usd = models.DecimalField(max_digits=18, decimal_places=8)
    charged_usd = models.DecimalField(max_digits=18, decimal_places=8, null=True)
    status = models.CharField(max_length=12, default="reserved")
    created_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True)

    class Meta:
        indexes = [
            models.Index(fields=["sector", "period"]),
            models.Index(fields=["user_id_snapshot", "period"]),
            models.Index(fields=["meeting_id", "created_at"]),
        ]
