"""Operational events, separate from user/security actions and AI billing."""

from django.conf import settings
from django.db import models


class SystemEvent(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    component = models.CharField(max_length=40)
    event_code = models.CharField(max_length=64)
    severity = models.CharField(max_length=12, default="info")
    outcome = models.CharField(max_length=20, blank=True)
    error_code = models.CharField(max_length=60, blank=True)
    stage = models.CharField(max_length=40, blank=True)
    kind = models.CharField(max_length=30, blank=True)
    job_id = models.UUIDField(null=True, blank=True)
    meeting_id = models.UUIDField(null=True, blank=True)
    sector = models.ForeignKey("accounts.Sector", null=True, on_delete=models.SET_NULL)
    sector_id_snapshot = models.PositiveBigIntegerField(null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    user_id_snapshot = models.PositiveBigIntegerField(null=True, blank=True)
    request_id = models.UUIDField(null=True, blank=True)
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["job_id", "created_at"]),
            models.Index(fields=["meeting_id", "created_at"]),
        ]
