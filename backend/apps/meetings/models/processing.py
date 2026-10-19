from django.conf import settings
from django.db import models

from .meeting import Meeting


class ProcessingJob(models.Model):
    """Durable per-request lifecycle; never stores audio or generated files."""

    id = models.UUIDField(primary_key=True)
    meeting_id = models.UUIDField()
    sector = models.ForeignKey("accounts.Sector", on_delete=models.PROTECT)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    kind = models.CharField(max_length=30)
    status = models.CharField(max_length=20, default="queued")
    stage = models.CharField(max_length=40, blank=True)
    completed_units = models.PositiveIntegerField(default=0)
    total_units = models.PositiveIntegerField(null=True, blank=True)
    media_duration_seconds = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    error_code = models.CharField(max_length=60, blank=True)
    queued_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancel_requested_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-queued_at"]
        indexes = [
            models.Index(fields=["queued_at"]),
            models.Index(fields=["sector", "queued_at"]),
            models.Index(fields=["requested_by", "queued_at"]),
            models.Index(fields=["status", "heartbeat_at"]),
        ]

class SpeakerAnalysis(models.Model):
    """Durable, owner-scoped lifecycle and quota for optional voice comparison."""

    meeting = models.OneToOneField(
        Meeting, on_delete=models.CASCADE, related_name="speaker_analysis"
    )
    uses = models.PositiveSmallIntegerField(default=0)
    job_id = models.UUIDField(null=True, blank=True)
    version = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, default="none")
    groups = models.JSONField(default=list)
    caution = models.BooleanField(default=False)
    sample_times = models.JSONField(default=dict)
    message = models.CharField(max_length=200, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(uses__lte=2), name="speaker_analysis_max_two_uses"
            ),
        ]
