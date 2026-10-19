from redis.exceptions import RedisError
from rest_framework.exceptions import APIException
from rest_framework.throttling import UserRateThrottle

from apps.audit.system_recording import record_system_event


class RateLimitUnavailable(APIException):
    status_code = 503
    default_detail = "Serviço temporariamente indisponível. Tente novamente mais tarde."
    default_code = "rate_limit_unavailable"


class AvailableUserRateThrottle(UserRateThrottle):
    """Fail closed with a controlled response when Redis rate limiting is down."""

    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except RedisError:
            actor = request.user if request.user.is_authenticated else None
            record_system_event(
                "cache", "rate_limit_unavailable", severity="error", outcome="failed",
                user_id=actor.pk if actor else None,
            )
            raise RateLimitUnavailable() from None


class UploadThrottle(AvailableUserRateThrottle):
    scope = "upload"
