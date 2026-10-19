"""Request metadata audit for mutations; never records request bodies or query strings."""

import logging
import uuid

from .models import record_audit
from .recording import request_ips
from .system_recording import record_system_event

logger = logging.getLogger(__name__)


class MutationAuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.audit_request_id = uuid.uuid4()
        response = self.get_response(request)
        response["X-Request-ID"] = str(request.audit_request_id)
        path = request.path
        if response.status_code >= 500:
            actor = request.user if request.user.is_authenticated else None
            client_ip, _ = request_ips(request)
            record_system_event(
                "http", "http_5xx", severity="error", outcome="failed",
                http_status=response.status_code, request_id=request.audit_request_id,
                user_id=actor.pk if actor else None,
                sector_id=(actor.membership.sector_id if actor and
                           hasattr(actor, "membership") else None),
                client_ip=client_ip,
            )
        if (
            request.method not in ("POST", "PATCH", "PUT", "DELETE")
            or not path.startswith(("/api/v1/", "/api/admin/"))
            or path in ("/api/v1/login/", "/api/v1/logout/", "/api/v1/account/password/")
        ):
            return response
        try:
            actor = request.user if request.user.is_authenticated else None
            record_audit(
                actor, "api_mutation", request=request,
                outcome="success" if response.status_code < 400 else "failed",
                target_type="endpoint", target_ref=path,
                details={"method": request.method, "status": response.status_code},
            )
        except Exception:
            logger.exception("Could not persist API mutation audit event")
        return response
