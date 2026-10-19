"""A public, fixed bootstrap credential must never be usable on a LAN bind."""

import ipaddress
import os

from django.contrib.auth import get_user_model


def unsafe_bootstrap_bind():
    """Return the unsafe bind variable, or None when both listeners are local."""
    for label in ("PUBLIC_BIND_IP", "ADMIN_BIND_IP"):
        try:
            if not ipaddress.ip_address(os.getenv(label, "127.0.0.1")).is_loopback:
                return label
        except ValueError:
            return label
    return None


def initial_login_forbidden(username):
    """Reject a pending bootstrap identity before checking a known password."""
    return bool(unsafe_bootstrap_bind()) and get_user_model().objects.filter(
        username=username, membership__must_change_password=True,
    ).exists()
