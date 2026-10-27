"""Atomic, best-effort USD admission control around provider calls.

The local ledger is an estimate, not the provider's invoice. Unknown-cost calls
retain their reservation so they cannot silently free capacity.
"""

import logging
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.db.models import Case, DecimalField, F, Sum, When
from django.utils import timezone

from apps.accounts.models import Sector, UserMembership
from apps.audit.models import AIBudgetEntry, AIUsageEvent
from apps.audit.system_recording import record_system_event
from apps.audit.usage import _usage_dict, estimate_cost, record_openai_failure, record_openai_usage

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")
SCALE = Decimal("0.00000001")


class AIBudgetExceeded(Exception):
    """A configured local user or sector estimate has no available capacity."""

    def __init__(self, message, scope):
        super().__init__(message)
        self.scope = scope


def current_period(now=None):
    local = timezone.localtime(now or timezone.now(), ZoneInfo(settings.TIME_ZONE))
    return local.date().replace(day=1)


def _period_bounds(period):
    year = period.year + (period.month == 12)
    month = period.month % 12 + 1
    tz = ZoneInfo(settings.TIME_ZONE)
    return (
        timezone.make_aware(datetime.combine(period, time.min), tz),
        timezone.make_aware(datetime(year, month, 1), tz),
    )


def _money(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Reserva de IA inválida") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("Reserva de IA inválida")
    try:
        amount = amount.quantize(SCALE)
    except InvalidOperation as exc:
        raise ValueError("Reserva de IA inválida") from exc
    if amount <= 0 or amount >= Decimal("10000000000"):
        raise ValueError("Reserva de IA inválida")
    return amount


def _spent(*, period, sector_id, user_id=None):
    """New entries plus historical/unlinked usage; never count linked rows twice."""
    entries = AIBudgetEntry.objects.filter(period=period, sector_id=sector_id)
    legacy = AIUsageEvent.objects.filter(
        sector_id=sector_id, budget_entry__isnull=True,
        created_at__gte=_period_bounds(period)[0],
        created_at__lt=_period_bounds(period)[1],
    )
    if user_id is not None:
        entries = entries.filter(user_id_snapshot=user_id)
        legacy = legacy.filter(requested_by_id=user_id)
    entry_sum = entries.aggregate(value=Sum(Case(
        When(status="reserved", then=F("reserved_usd")),
        default=F("charged_usd"), output_field=DecimalField(max_digits=18, decimal_places=8),
    )))['value'] or Decimal(0)
    legacy_sum = legacy.aggregate(value=Sum("estimated_usd"))["value"] or Decimal(0)
    return entry_sum + legacy_sum


def budget_snapshot(sector_id, user_id=None):
    """Administrative, current-month estimate for a selected sector/member."""
    period = current_period()
    sector = Sector.objects.get(pk=sector_id)
    sector_spent = _spent(period=period, sector_id=sector_id)
    result = {
        "period": period.strftime("%Y-%m"), "sector_id": sector_id,
        "sector_limit_usd": sector.monthly_ai_budget_usd,
        "sector_used_usd": sector_spent,
        "sector_remaining_usd": (
            max(Decimal(0), sector.monthly_ai_budget_usd - sector_spent)
            if sector.monthly_ai_budget_usd is not None else None
        ),
    }
    if user_id is not None:
        membership = UserMembership.objects.get(user_id=user_id, sector_id=sector_id)
        user_spent = _spent(period=period, sector_id=sector_id, user_id=user_id)
        result.update({
            "user_id": user_id,
            "user_limit_usd": membership.monthly_ai_budget_usd,
            "user_used_usd": user_spent,
            "user_remaining_usd": (
                max(Decimal(0), membership.monthly_ai_budget_usd - user_spent)
                if membership.monthly_ai_budget_usd is not None else None
            ),
        })
    return result


def reserve_ai_call(context, estimate_usd):
    if not context:
        return None
    try:
        return _reserve_ai_call(context, estimate_usd)
    except AIBudgetExceeded as exc:
        record_system_event(
            "worker", "ai_budget_denied", severity="warning", outcome="denied",
            error_code=f"{exc.scope}_monthly_budget", kind=context["operation"],
            job_id=context.get("job_id"), meeting_id=context["meeting_id"],
            sector_id=context["sector_id"], user_id=context["user_id"],
        )
        raise


def check_budget_available(sector_id, user_id=None):
    """Cheap queue preflight; per-call atomic reservations remain authoritative."""
    snapshot = budget_snapshot(sector_id, user_id)
    for scope in ("sector", "user"):
        remaining = snapshot.get(f"{scope}_remaining_usd")
        if remaining is not None and remaining <= 0:
            raise AIBudgetExceeded(
                "Teto mensal estimado de IA atingido. Consulte o administrador.", scope,
            )


@transaction.atomic
def _reserve_ai_call(context, estimate_usd):
    """Serialize budget admission by sector row (and the member's current limit)."""
    amount = _money(estimate_usd)
    sector_id, user_id = context["sector_id"], context["user_id"]
    sector = Sector.objects.select_for_update().get(pk=sector_id)
    membership = UserMembership.objects.select_for_update().get(
        user_id=user_id, sector_id=sector_id
    )
    period = current_period()
    if sector.monthly_ai_budget_usd is not None:
        if _spent(period=period, sector_id=sector_id) + amount > sector.monthly_ai_budget_usd:
            raise AIBudgetExceeded("Teto mensal de IA do setor atingido.", "sector")
    if membership.monthly_ai_budget_usd is not None:
        if (_spent(period=period, sector_id=sector_id, user_id=user_id) + amount
                > membership.monthly_ai_budget_usd):
            raise AIBudgetExceeded("Teto mensal de IA do usuário atingido.", "user")
    return AIBudgetEntry.objects.create(
        sector=sector, requested_by_id=user_id, user_id_snapshot=user_id,
        meeting_id=context["meeting_id"], job_id=context.get("job_id"),
        period=period, operation=context["operation"], reserved_usd=amount,
    )


@transaction.atomic
def settle_ai_call(entry, actual_usd):
    if entry is None:
        return
    actual = None if actual_usd is None else (
        Decimal(0) if actual_usd == 0 else _money(actual_usd)
    )
    # Same lock/order as admission: a late higher estimate must not race another
    # admission. No database lock is held during the external request.
    Sector.objects.select_for_update().get(pk=entry.sector_id)
    AIBudgetEntry.objects.filter(pk=entry.pk, status="reserved").update(
        status="settled" if actual is not None else "unpriced",
        charged_usd=actual if actual is not None else entry.reserved_usd,
        settled_at=timezone.now(),
    )


def estimate_text_reservation(model, text, output_tokens):
    """Conservative local buffer from UTF-8 bytes; tariff may still change."""
    from apps.audit.usage import RATES

    rates = RATES.get(model)
    if rates is None:
        return Decimal("1.00")
    input_rate, output_rate, _ = rates
    if model == "gpt-6-luna":
        input_rate *= 2
        output_rate *= Decimal("1.5")
    input_bytes = len(text.encode("utf-8")) + 16384  # prompt/schema/wrapper margin
    amount = (Decimal(input_bytes) * input_rate
              + Decimal(output_tokens) * output_rate) / Decimal(1_000_000)
    return max(CENT, (amount * 2).quantize(SCALE))


def estimate_audio_reservation(size_bytes):
    """Admission buffer only; compressed bytes are not billable audio units."""
    return max(Decimal("0.10"), (
        Decimal(size_bytes) / Decimal(1_000_000) * Decimal("0.05")
    ).quantize(SCALE))


def tracked_openai_call(call, context, model, source_label="", *, reservation_usd=None):
    """One ledger event per SDK attempt (SDK retries are disabled in _client)."""
    entry = reserve_ai_call(
        context, Decimal("0.10") if reservation_usd is None else reservation_usd
    )
    try:
        response = call()
    except Exception as exc:
        record_openai_failure(exc, context, model, source_label, entry)
        try:
            settle_ai_call(entry, None)
        except Exception:
            logger.exception("Could not settle failed AI budget reservation")
        raise
    record_openai_usage(response, context, model, source_label, entry)
    amount, _, _ = estimate_cost(model, _usage_dict(response))
    try:
        settle_ai_call(entry, amount)
    except Exception:
        logger.exception("Could not settle AI budget reservation")
    return response
