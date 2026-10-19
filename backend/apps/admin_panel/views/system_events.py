"""Admin-only operational diagnostics; no request or model payloads."""

from django.db.models import Q
from django.utils.dateparse import parse_date
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from apps.admin_panel.permissions import ActiveStaff
from apps.audit.models import SystemEvent

from ..filters import _positive_int
from ..serializers.system_events import SystemEventSerializer


class SystemEventAdminViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [ActiveStaff]
    serializer_class = SystemEventSerializer
    queryset = SystemEvent.objects.all()

    def get_queryset(self):
        qs = SystemEvent.objects.select_related("user", "sector")
        params = self.request.query_params
        if params.get("sector_id"):
            sector_id = _positive_int(params["sector_id"], "sector_id")
            qs = qs.filter(Q(sector_id=sector_id) | Q(sector_id_snapshot=sector_id))
        if params.get("user_id"):
            user_id = _positive_int(params["user_id"], "user_id")
            qs = qs.filter(Q(user_id=user_id) | Q(user_id_snapshot=user_id))
        for key in ("component", "event_code", "severity", "kind", "error_code"):
            if params.get(key):
                qs = qs.filter(**{key: params[key][:64]})
        for key in ("job_id", "meeting_id"):
            if params.get(key):
                from uuid import UUID

                try:
                    value = UUID(params[key])
                except ValueError:
                    raise ValidationError({key: "UUID inválido."}) from None
                qs = qs.filter(**{key: value})
        for key, lookup in (("from_date", "created_at__date__gte"),
                            ("to_date", "created_at__date__lte")):
            if params.get(key):
                date = parse_date(params[key])
                if date is None:
                    raise ValidationError({key: "Data inválida; use AAAA-MM-DD."})
                qs = qs.filter(**{lookup: date})
        return qs.order_by("-created_at", "-id")
