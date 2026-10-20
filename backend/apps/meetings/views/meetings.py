
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from apps.accounts.models import UserMembership
from apps.audit.change_tracking import fingerprint
from apps.audit.models import record_audit

from ..access import manageable_meetings, readable_meetings
from ..correction_jobs import active_key
from ..models import Meeting, MeetingStatus, Minutes, SpeakerAnalysis
from ..serializers import (
    MeetingSerializer,
    SharingSerializer,
    TransferSerializer,
)
from ..services import (
    Conflict,
)
from ..services.deletion import request_deletion
from .common import _require_sector_key


class MeetingsMixin:
    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        record_audit(request.user, "meeting_viewed", kwargs.get("pk"), request=request)
        return response

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Meeting.objects.none()
        qs = (
            (
                readable_meetings(self.request.user)
                if self.request.method in ("GET", "HEAD", "OPTIONS")
                else manageable_meetings(self.request.user)
            )
            .annotate(
                speaker_count=Count(
                    "speakers", filter=Q(speakers__merged_into__isnull=True), distinct=True
                ),
                duration_ms=Max("segments__end_ms"),
            )
            .order_by("-created_at", "-id")
        )
        state = self.request.query_params.get("status")
        if state:
            if state not in MeetingStatus.values:
                raise ValidationError({"status": "Estado inválido."})
            qs = qs.filter(status=state)
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(title__icontains=search[:100])
        return qs

    def perform_create(self, serializer):
        membership = UserMembership.objects.select_related("sector").filter(
            user=self.request.user, sector__is_active=True
        ).first()
        if membership is None:
            raise ValidationError({"sector": "Usuário sem setor ativo."})
        _require_sector_key(membership.sector_id)
        with transaction.atomic():
            serializer.save(
                owner=self.request.user,
                created_by=self.request.user,
                sector=membership.sector,
                staged_at=(timezone.now()
                           if self.request.headers.get("X-Staged-Upload") == "1" else None),
            )
            record_audit(self.request.user, "meeting_created", serializer.instance.id,
                         request=self.request)

    def perform_update(self, serializer):
        with transaction.atomic():
            meeting = Meeting.objects.select_for_update().get(pk=serializer.instance.pk)
            if meeting.owner_id != self.request.user.pk or meeting.deletion_requested_at:
                raise NotFound()
            old_title = meeting.title
            for field, value in serializer.validated_data.items():
                setattr(meeting, field, value)
            meeting.save(update_fields=[*serializer.validated_data.keys(), "updated_at"])
            serializer.instance = meeting
            if meeting.title != old_title:
                record_audit(
                    self.request.user, "meeting_renamed", meeting.id,
                    request=self.request, sector=meeting.sector,
                    target_type="meeting", target_ref=meeting.id,
                    details={"title_before": fingerprint(old_title),
                             "title_after": fingerprint(meeting.title)},
                )

    def perform_destroy(self, instance):
        request_deletion(instance.id, self.request.user, self.request)

    @extend_schema(request=SharingSerializer, responses={200: MeetingSerializer})
    @action(detail=True, methods=["patch"], url_path="sharing")
    def sharing(self, request, pk=None):
        meeting = self.get_object()
        serializer = SharingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            current = Meeting.objects.select_for_update().get(pk=meeting.pk)
            if current.owner_id != request.user.pk or current.deletion_requested_at:
                raise NotFound()
            if current.access_version != serializer.validated_data["access_version"]:
                raise Conflict()
            shared_before = current.shared_with_sector
            current.shared_with_sector = serializer.validated_data["shared_with_sector"]
            current.access_version += 1
            current.save(update_fields=["shared_with_sector", "access_version", "updated_at"])
            record_audit(
                request.user, "meeting_sharing_changed", current.id,
                request=request, sector=current.sector,
                target_type="meeting", target_ref=current.id,
                details={"shared_before": shared_before,
                         "shared_after": current.shared_with_sector,
                         "access_version": current.access_version},
            )
        return Response(MeetingSerializer(current, context={"request": request}).data)

    @extend_schema(request=TransferSerializer, responses={200: MeetingSerializer})
    @action(detail=True, methods=["post"], url_path="transfer")
    def transfer(self, request, pk=None):
        meeting = self.get_object()
        serializer = TransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            current = Meeting.objects.select_for_update().get(pk=meeting.pk)
            if current.owner_id != request.user.pk or current.deletion_requested_at:
                raise NotFound()
            if current.access_version != serializer.validated_data["access_version"]:
                raise Conflict()
            if current.status not in (MeetingStatus.TRANSCRITO, MeetingStatus.ATA_PRONTA):
                raise Conflict("Aguarde o término do processamento antes da transferência.")
            if (
                SpeakerAnalysis.objects.filter(meeting=current, status="processing").exists()
                or Minutes.objects.filter(meeting=current, mind_map_status="generating").exists()
                or cache.get(active_key(current.id, current.transcription_version))
            ):
                raise Conflict("Aguarde o término das análises antes da transferência.")
            target = UserMembership.objects.filter(
                user_id=serializer.validated_data["target_user_id"],
                user__is_active=True,
                sector_id=current.sector_id,
                sector__is_active=True,
            ).first()
            if target is None or target.user_id == request.user.pk:
                raise ValidationError({"target_user_id": "Escolha outro membro ativo do setor."})
            previous_owner_id = current.owner_id
            current.owner_id = target.user_id
            current.access_version += 1
            current.save(update_fields=["owner", "access_version", "updated_at"])
            record_audit(
                request.user, "meeting_transferred", current.id,
                request=request, sector=current.sector, subject_user=target.user,
                target_type="meeting", target_ref=current.id,
                details={"from_user_id": previous_owner_id, "to_user_id": target.user_id},
            )
        return Response(MeetingSerializer(current, context={"request": request}).data)
