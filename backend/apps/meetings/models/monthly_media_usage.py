from django.conf import settings
from django.db import models


class MonthlyMediaUsage(models.Model):
    """Accepted upload duration, by original uploader and calendar month."""

    sector = models.ForeignKey("accounts.Sector", on_delete=models.PROTECT)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    user_id_snapshot = models.PositiveBigIntegerField()
    period = models.DateField()
    used_seconds = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    upload_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sector", "user_id_snapshot", "period"],
                name="unique_monthly_media_usage",
            ),
            models.CheckConstraint(
                condition=models.Q(used_seconds__gte=0), name="monthly_media_seconds_nonnegative"
            ),
        ]
