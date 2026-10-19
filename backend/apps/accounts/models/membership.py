from django.conf import settings
from django.db import models

from .sector import Sector


class UserMembership(models.Model):
    """One-to-one, rather than M2M, enforces at most one sector per user."""

    class AuthSource(models.TextChoices):
        LOCAL = "local", "Local"
        LDAP = "ldap", "LDAP futuro"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membership"
    )
    sector = models.ForeignKey(Sector, on_delete=models.PROTECT, related_name="members")
    auth_source = models.CharField(
        max_length=12, choices=AuthSource.choices, default=AuthSource.LOCAL
    )
    external_id = models.CharField(max_length=200, blank=True)
    session_version = models.PositiveIntegerField(default=0)
    must_change_password = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["auth_source", "external_id"],
                condition=~models.Q(external_id=""),
                name="unique_nonempty_external_identity",
            ),
        ]
