from django.conf import settings
from django.db import models

from .sector import Sector


class UserMembership(models.Model):
    """One-to-one, rather than M2M, enforces at most one sector per user."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membership"
    )
    sector = models.ForeignKey(Sector, on_delete=models.PROTECT, related_name="members")
    session_version = models.PositiveIntegerField(default=0)
    must_change_password = models.BooleanField(default=False)
    bootstrap_local_only = models.BooleanField(default=False)
    monthly_ai_budget_usd = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
