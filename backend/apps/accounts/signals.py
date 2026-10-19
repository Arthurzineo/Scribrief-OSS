from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import UserMembership


@receiver(user_logged_in)
def stamp_account_session_version(sender, request, user, **kwargs):
    version = (
        UserMembership.objects.filter(user=user)
        .values_list("session_version", flat=True)
        .first()
    )
    if version is not None:
        request.session["account_session_version"] = version
