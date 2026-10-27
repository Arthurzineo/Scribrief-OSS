"""Read-only administrative audit and estimated OpenAI usage reports."""

import uuid

from django.db.models import Case, Count, DecimalField, F, Max, Q, Sum, When
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.models import Sector, UserMembership
from apps.accounts.services.ai_budget import budget_snapshot
from apps.admin_panel.permissions import ActiveStaff
from apps.audit.models import AIBudgetEntry, AIUsageEvent
from apps.meetings.models import Meeting

from ..filters import _positive_int
from ..serializers.usage import AIBudgetSnapshotSerializer, UsageEventSerializer


class UsageAdminViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [ActiveStaff]
    serializer_class = UsageEventSerializer
    queryset = AIUsageEvent.objects.all()

    def get_queryset(self):
        qs = AIUsageEvent.objects.select_related("sector", "requested_by")
        params = self.request.query_params
        for parameter, field in (("sector_id", "sector_id"), ("user_id", "requested_by_id")):
            if params.get(parameter):
                qs = qs.filter(**{field: _positive_int(params[parameter], parameter)})
        if params.get("meeting_id"):
            try:
                meeting_id = uuid.UUID(params["meeting_id"])
            except ValueError as exc:
                raise ValidationError({"meeting_id": "Identificador inválido."}) from exc
            qs = qs.filter(meeting_id=meeting_id)
        if params.get("operation"):
            qs = qs.filter(operation=params["operation"][:40])
        return qs.order_by("-created_at", "-id")

    @extend_schema(
        parameters=[
            OpenApiParameter("sector_id", int, required=True),
            OpenApiParameter("user_id", int, required=False),
        ],
        responses=AIBudgetSnapshotSerializer,
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def budget(self, request):
        sector_id = _positive_int(request.query_params.get("sector_id"), "sector_id")
        user_raw = request.query_params.get("user_id")
        user_id = _positive_int(user_raw, "user_id") if user_raw else None
        if not Sector.objects.filter(pk=sector_id).exists():
            raise ValidationError({"sector_id": "Setor não encontrado."})
        if user_id and not UserMembership.objects.filter(
            sector_id=sector_id, user_id=user_id
        ).exists():
            raise ValidationError({"user_id": "Usuário não pertence ao setor."})
        return Response(AIBudgetSnapshotSerializer(budget_snapshot(sector_id, user_id)).data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        qs = self.get_queryset()
        totals = qs.aggregate(
            calls=Count("id"), estimated_total_usd=Sum("estimated_usd"),
            failed=Count("id", filter=Q(outcome="failed")),
            unavailable=Count("id", filter=Q(estimate_status="unavailable")),
            minutes_usd=Sum("estimated_usd", filter=Q(operation="minutes")),
            input_tokens_sum=Sum("input_tokens"), output_tokens_sum=Sum("output_tokens"),
            total_tokens_sum=Sum("total_tokens"),
            token_calls=Count("id", filter=Q(total_tokens__isnull=False)),
        )
        for name in ("input_tokens", "output_tokens", "total_tokens"):
            totals[name] = totals.pop(f"{name}_sum")
        by_user = list(qs.values("requested_by_id", "requested_by__username").annotate(
            calls=Count("id"), estimated_total_usd=Sum("estimated_usd"),
            total_tokens_sum=Sum("total_tokens"),
            token_calls=Count("id", filter=Q(total_tokens__isnull=False)),
        ).order_by("requested_by__username")[:1000])
        for row in by_user:
            row["total_tokens"] = row.pop("total_tokens_sum")
        by_sector = list(qs.values("sector_id", "sector__name").annotate(
            calls=Count("id"), estimated_total_usd=Sum("estimated_usd"),
            total_tokens_sum=Sum("total_tokens"),
            token_calls=Count("id", filter=Q(total_tokens__isnull=False)),
        ).order_by("sector__name")[:1000])
        for row in by_sector:
            row["total_tokens"] = row.pop("total_tokens_sum")
        return Response({"totals": totals, "by_user": by_user, "by_sector": by_sector})

    @action(detail=False, methods=["get"])
    def meetings(self, request):
        """Paginated per-meeting ledger totals, including unknown-price calls."""
        qs = self.get_queryset().order_by()
        grouped = qs.values("meeting_id").annotate(
            calls=Count("id"),
            known_cost_usd=Sum("estimated_usd"),
            unpriced_calls=Count("id", filter=Q(estimated_usd__isnull=True)),
            failed_calls=Count("id", filter=Q(outcome="failed")),
            latest_at=Max("created_at"),
        ).order_by("-latest_at", "meeting_id")
        page = self.paginate_queryset(grouped)
        if page is None:
            page = list(grouped[:100])
        ids = [row["meeting_id"] for row in page]
        titles = dict(Meeting.objects.filter(id__in=ids).values_list("id", "title"))
        budget_rows = AIBudgetEntry.objects.filter(
            meeting_id__in=ids, pk__in=qs.values("budget_entry_id"),
        ).values(
            "meeting_id", "operation"
        ).annotate(
            local_budget_usd=Sum(Case(
                When(status="reserved", then=F("reserved_usd")),
                default=F("charged_usd"),
                output_field=DecimalField(max_digits=18, decimal_places=8),
            )),
            unpriced_calls=Count("id", filter=Q(status="unpriced")),
        )
        budget_by_operation = {
            (row["meeting_id"], row["operation"]): row for row in budget_rows
        }
        breakdown = qs.filter(meeting_id__in=ids).values(
            "meeting_id", "operation"
        ).annotate(
            calls=Count("id"), known_cost_usd=Sum("estimated_usd"),
            unpriced_calls=Count("id", filter=Q(estimated_usd__isnull=True)),
            failed_calls=Count("id", filter=Q(outcome="failed")),
        ).order_by("operation")
        operations = {meeting_id: [] for meeting_id in ids}
        for row in breakdown:
            budget_row = budget_by_operation.get((row["meeting_id"], row["operation"]))
            operations[row["meeting_id"]].append({
                "operation": row["operation"], "calls": row["calls"],
                "estimated_usd": row["known_cost_usd"],
                "unpriced_calls": row["unpriced_calls"],
                "failed_calls": row["failed_calls"],
                "local_budget_usd": (
                    budget_row["local_budget_usd"] if budget_row else None
                ),
            })
        results = [{
            "meeting_id": str(row["meeting_id"]),
            "title": titles.get(row["meeting_id"]),
            "calls": row["calls"],
            "estimated_usd": row["known_cost_usd"],
            "unpriced_calls": row["unpriced_calls"],
            "failed_calls": row["failed_calls"],
            "local_budget_usd": sum(
                (item["local_budget_usd"] or 0) for item in operations[row["meeting_id"]]
            ),
            "budget_unpriced_calls": sum(
                budget_by_operation.get((row["meeting_id"], item["operation"]), {}).get(
                    "unpriced_calls", 0
                ) for item in operations[row["meeting_id"]]
            ),
            "latest_at": row["latest_at"],
            "operations": operations[row["meeting_id"]],
        } for row in page]
        return self.get_paginated_response(results) if self.paginator else Response({
            "count": len(results), "next": None, "previous": None, "results": results,
        })
