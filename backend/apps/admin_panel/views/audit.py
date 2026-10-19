"""Read-only administrative audit and estimated OpenAI usage reports."""

import json
from uuid import UUID

from django.db.models import Q
from django.http import StreamingHttpResponse
from django.utils.dateparse import parse_date
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError

from apps.admin_panel.permissions import ActiveStaff
from apps.audit.models import AuditEvent, record_audit

from ..filters import _positive_int
from ..serializers.audit import AuditEventSerializer


class AuditAdminViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [ActiveStaff]
    serializer_class = AuditEventSerializer
    queryset = AuditEvent.objects.all()

    def get_queryset(self):
        qs = AuditEvent.objects.select_related("actor", "subject_user", "sector")
        params = self.request.query_params
        for parameter in ("sector_id", "actor_id", "subject_user_id"):
            if params.get(parameter):
                value = _positive_int(params[parameter], parameter)
                qs = qs.filter(Q(**{parameter: value}) | Q(**{f"{parameter}_snapshot": value}))
        if params.get("action"):
            qs = qs.filter(action=params["action"][:48])
        if params.get("target_id"):
            try:
                target_id = UUID(params["target_id"])
            except ValueError:
                raise ValidationError({"target_id": "UUID inválido."}) from None
            qs = qs.filter(target_id=target_id)
        for parameter, lookup in (("from_date", "created_at__date__gte"),
                                  ("to_date", "created_at__date__lte")):
            if params.get(parameter):
                date = parse_date(params[parameter])
                if date is None:
                    raise ValidationError({parameter: "Data inválida; use AAAA-MM-DD."})
                qs = qs.filter(**{lookup: date})
        return qs.order_by("-created_at", "-id")

    @action(detail=False, methods=["get"])
    def export(self, request):
        """Bounded JSONL export; never exports request bodies, secrets or media."""
        events = list(self.get_queryset()[:10_001])
        if len(events) > 10_000:
            raise ValidationError({"export": "Reduza o intervalo: máximo de 10.000 eventos."})
        record_audit(
            request.user, "audit_export", request=request, target_type="audit",
            details={"count": len(events)},
        )
        def lines():
            for event in events:
                yield json.dumps({
                    "id": event.pk, "when": event.created_at.isoformat(),
                    "actor_id": event.actor_id_snapshot, "sector_id": event.sector_id_snapshot,
                    "subject_user_id": event.subject_user_id_snapshot,
                    "action": event.action, "outcome": event.outcome,
                    "target_type": event.target_type, "target_ref": event.target_ref,
                    "client_ip": event.client_ip, "peer_ip": event.peer_ip,
                    "details": event.details,
                    "request_id": str(event.request_id) if event.request_id else None,
                }, ensure_ascii=False) + "\n"
        response = StreamingHttpResponse(lines(), content_type="application/x-ndjson")
        response["Content-Disposition"] = 'attachment; filename="scribrief-audit.jsonl"'
        response["X-Content-Type-Options"] = "nosniff"
        return response
