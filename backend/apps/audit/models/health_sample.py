from django.db import models


class HealthSample(models.Model):
    """Sanitized periodic observations; absence of rows is unknown, not downtime."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    services = models.JSONField(default=dict)
    disk_total_bytes = models.PositiveBigIntegerField(null=True)
    disk_used_bytes = models.PositiveBigIntegerField(null=True)
    disk_free_bytes = models.PositiveBigIntegerField(null=True)

    class Meta:
        ordering = ["-created_at"]
