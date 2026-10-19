from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.exceptions import ImproperlyConfigured
from django.db.models import F
from django.utils import timezone

from apps.accounts.models import UserMembership


def revoke_user_sessions(user_id):
    """Bump the authoritative epoch, then remove currently stored DB sessions."""
    if settings.SESSION_ENGINE != "django.contrib.sessions.backends.db":
        raise ImproperlyConfigured("Account session revocation requires database sessions.")
    UserMembership.objects.filter(user_id=user_id).update(session_version=F("session_version") + 1)
    keys = []
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator(chunk_size=500):
        if str(session.get_decoded().get("_auth_user_id")) == str(user_id):
            keys.append(session.session_key)
            if len(keys) == 500:
                Session.objects.filter(session_key__in=keys).delete()
                keys.clear()
    if keys:
        Session.objects.filter(session_key__in=keys).delete()
