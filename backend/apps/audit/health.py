"""Bounded, sanitized operational probes for the administrative dashboard."""

import shutil
from http.client import HTTPConnection, HTTPSConnection
from urllib.parse import urlsplit

from django.conf import settings
from django.db import connection
from django.utils import timezone
from redis import Redis

from config.celery import app as celery_app

from .models import HealthSample


def _http_ok(url, *, host_header=None):
    try:
        target = urlsplit(url)
        if target.scheme not in {"http", "https"} or not target.hostname:
            return False
        connection_type = HTTPSConnection if target.scheme == "https" else HTTPConnection
        client = connection_type(target.hostname, target.port, timeout=1.5)
        try:
            client.request("GET", target.path or "/",
                           headers={"Host": host_header} if host_header else {})
            return client.getresponse().status == 200
        finally:
            client.close()
    except Exception:
        return False


def collect_live_health(*, from_worker=False):
    """Only fixed service names and aggregate capacity leave this function."""
    # The backend's internal DNS name is not a public allowed host. Use a fixed
    # loopback Host header while connecting to that container's private address.
    backend_ok = True  # This authenticated request itself proves the backend responded.
    if from_worker:
        backend_ok = _http_ok(settings.HEALTH_BACKEND_URL, host_header="127.0.0.1")
    services = {"backend": "ok" if backend_ok else "down"}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        services["database"] = "ok"
    except Exception:
        services["database"] = "down"
    try:
        client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1,
                                socket_timeout=1)
        services["redis"] = "ok" if client.ping() else "down"
        client.close()
    except Exception:
        services["redis"] = "down"
    services["frontend"] = "ok" if _http_ok(settings.HEALTH_FRONTEND_URL) else "down"
    if from_worker:
        services["worker"] = "ok"
    else:
        try:
            replies = celery_app.control.inspect(timeout=1.5).ping() or {}
            services["worker"] = "ok" if replies else "down"
        except Exception:
            services["worker"] = "down"
    disk = {"total_bytes": None, "used_bytes": None, "free_bytes": None}
    try:
        usage = shutil.disk_usage(settings.MEDIA_ROOT)
        disk = {"total_bytes": usage.total, "used_bytes": usage.used,
                "free_bytes": usage.free}
        services["storage"] = "ok"
    except Exception:
        services["storage"] = "down"
    return {"checked_at": timezone.now(), "services": services, "disk": disk}


def save_health_sample():
    observation = collect_live_health(from_worker=True)
    return HealthSample.objects.create(
        services=observation["services"],
        disk_total_bytes=observation["disk"]["total_bytes"],
        disk_used_bytes=observation["disk"]["used_bytes"],
        disk_free_bytes=observation["disk"]["free_bytes"],
    )
