import ipaddress

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from .models.event import AuditEvent


def _valid_ip(value):
    try:
        return str(ipaddress.ip_address(value))
    except (TypeError, ValueError):
        return None

def _trusted_proxy(peer_ip):
    if peer_ip is None:
        return False
    address = ipaddress.ip_address(peer_ip)
    for item in settings.AUDIT_TRUSTED_PROXY_CIDRS:
        try:
            if address in ipaddress.ip_network(item, strict=False):
                return True
        except ValueError:
            continue
    return False


def request_ips(request):
    if request is None:
        return None, None
    peer_ip = _valid_ip(request.META.get("REMOTE_ADDR"))
    client_ip = peer_ip
    if _trusted_proxy(peer_ip):
        client_ip = _valid_ip(request.META.get("HTTP_X_REAL_IP")) or peer_ip
    return client_ip, peer_ip

def record_audit(
    actor, action, target_id=None, outcome="success", *, request=None,
    sector=None, subject_user=None, target_type="", target_ref="", details=None,
):
    # Nginx overwrites X-Real-IP with its actual TCP peer. Never parse a client-
    # supplied X-Forwarded-For chain; preserve the backend peer separately.
    client_ip, peer_ip = request_ips(request)
    if sector is None and actor is not None:
        try:
            sector = actor.membership.sector
        except ObjectDoesNotExist:
            pass
    return AuditEvent.objects.create(
        actor=actor, action=action, target_id=target_id, outcome=outcome,
        actor_id_snapshot=actor.pk if actor is not None else None,
        client_ip=client_ip, peer_ip=peer_ip, sector=sector,
        sector_id_snapshot=sector.pk if sector is not None else None,
        subject_user=subject_user, target_type=target_type,
        subject_user_id_snapshot=subject_user.pk if subject_user is not None else None,
        target_ref=str(target_ref)[:100], details=details or {},
        request_id=getattr(request, "audit_request_id", None),
    )
