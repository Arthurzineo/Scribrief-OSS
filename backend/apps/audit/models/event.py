from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    # Preserve accountable numeric IDs if an account/sector is later removed.
    actor_id_snapshot = models.PositiveBigIntegerField(null=True, blank=True)
    action = models.CharField(max_length=48)
    target_id = models.UUIDField(null=True, blank=True)
    outcome = models.CharField(max_length=24)
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    peer_ip = models.GenericIPAddressField(null=True, blank=True)
    sector = models.ForeignKey("accounts.Sector", null=True, on_delete=models.SET_NULL)
    sector_id_snapshot = models.PositiveBigIntegerField(null=True, blank=True)
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="audit_subject_events",
    )
    subject_user_id_snapshot = models.PositiveBigIntegerField(null=True, blank=True)
    target_type = models.CharField(max_length=40, blank=True)
    target_ref = models.CharField(max_length=100, blank=True)
    details = models.JSONField(default=dict)
    request_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["created_at"])]
