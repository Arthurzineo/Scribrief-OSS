from rest_framework import viewsets

from ..models import Meeting
from ..serializers import MeetingSerializer
from .media import MediaMixin
from .meetings import MeetingsMixin
from .mind_map import MindMapMixin
from .minutes import MinutesMixin
from .processing import ProcessingMixin
from .speakers import SpeakersMixin
from .transcription import TranscriptionMixin


class MeetingViewSet(
    MeetingsMixin, ProcessingMixin, SpeakersMixin, TranscriptionMixin,
    MediaMixin, MinutesMixin, MindMapMixin, viewsets.ModelViewSet,
):
    queryset = Meeting.objects.none()  # Schema only; access is enforced in get_queryset.
    serializer_class = MeetingSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
