"""Read-only catalog of reviewed AI adapters for administrative key setup."""

from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.meetings.processing.ai_registry import AI_ADAPTERS, CAPABILITY_METHODS

from ..permissions import ActiveStaff


class AIProviderCatalogView(APIView):
    permission_classes = [ActiveStaff]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response({
            "providers": [
                {"id": provider_id, "capabilities": sorted(capabilities)}
                for provider_id, capabilities in sorted(AI_ADAPTERS.items())
            ],
            "selected": {
                capability: getattr(settings, f"AI_PROVIDER_{capability.upper()}", "openai")
                for capability in CAPABILITY_METHODS
            },
        })
