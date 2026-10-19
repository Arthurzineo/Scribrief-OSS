"""Administrative queue for reversible meeting deletion."""

from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.admin_panel.permissions import ActiveStaff
from apps.meetings.models import Meeting
from apps.meetings.services.deletion import restore_meeting

from ..serializers.deletions import PendingDeletionSerializer, RestoreDeletionSerializer


class PendingDeletionAdminViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [ActiveStaff]
    serializer_class = PendingDeletionSerializer
    queryset = Meeting.objects.none()

    def get_queryset(self):
        return (
            Meeting.objects.filter(deletion_requested_at__isnull=False)
            .select_related("owner", "sector")
            .order_by("deletion_requested_at", "id")
        )

    @extend_schema(request=RestoreDeletionSerializer, responses=PendingDeletionSerializer)
    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        serializer = RestoreDeletionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data["current_password"]):
            raise PermissionDenied("Confirme sua senha para restaurar a reunião.")
        meeting = restore_meeting(pk, request.user, request)
        return Response(PendingDeletionSerializer(meeting).data)
