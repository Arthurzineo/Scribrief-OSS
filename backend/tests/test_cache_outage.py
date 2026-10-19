from unittest.mock import patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from apps.audit.models import SystemEvent


@pytest.mark.django_db
def test_rate_limit_cache_outage_returns_controlled_503_not_500(api):
    with patch(
        "rest_framework.throttling.UserRateThrottle.cache.get",
        side_effect=RedisConnectionError("simulated cache outage"),
    ):
        response = api.get("/api/v1/meetings/")

    assert response.status_code == 503
    assert response.data["error"]["code"] == "rate_limit_unavailable"
    assert "simulated cache outage" not in str(response.data)
    assert SystemEvent.objects.filter(event_code="rate_limit_unavailable").exists()
