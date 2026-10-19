"""Atomic monthly upload accounting; deletion does not refund accepted media."""

import math
from datetime import date
from decimal import ROUND_UP, Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Sector

from ..models import MonthlyMediaUsage
from .common import Conflict


def current_period(now=None):
    instant = now or timezone.now()
    local = timezone.localtime(instant, ZoneInfo(settings.TIME_ZONE))
    return date(local.year, local.month, 1)


def billable_seconds(duration):
    if not isinstance(duration, (int, float, Decimal)) or not math.isfinite(float(duration)):
        raise ValueError("Duração inválida para a cota")
    if duration <= 0:
        raise ValueError("Duração inválida para a cota")
    return Decimal(str(duration)).quantize(Decimal("0.01"), rounding=ROUND_UP)


@transaction.atomic
def reserve_monthly_media(meeting, duration):
    """User-row lock serializes concurrent uploads, including the first in a month."""
    amount = billable_seconds(duration)
    get_user_model().objects.select_for_update().get(pk=meeting.owner_id)
    sector = Sector.objects.select_for_update().get(pk=meeting.sector_id)
    period = current_period()
    usage, _ = MonthlyMediaUsage.objects.select_for_update().get_or_create(
        sector=sector,
        user_id_snapshot=meeting.owner_id,
        period=period,
        defaults={"requested_by_id": meeting.owner_id},
    )
    limit = sector.max_monthly_minutes_per_user
    if limit is not None and usage.used_seconds + amount > Decimal(limit * 60):
        remaining = max(Decimal(0), Decimal(limit * 60) - usage.used_seconds)
        raise Conflict(
            "Cota mensal de mídia atingida para este usuário no setor. "
            f"Restam {remaining / 60:.2f} minutos neste mês; "
            f"o arquivo tem {amount / 60:.2f} minutos."
        )
    usage.used_seconds += amount
    usage.upload_count += 1
    usage.save(update_fields=["used_seconds", "upload_count", "updated_at"])
    return usage
