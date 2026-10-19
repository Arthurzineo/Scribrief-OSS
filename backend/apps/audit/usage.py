"""Safe OpenAI usage capture and explicitly estimated USD amounts."""

import logging
import re
from decimal import Decimal

from django.db import IntegrityError, transaction

from .change_tracking import fingerprint
from .models import AIUsageEvent

logger = logging.getLogger(__name__)

PRICING_VERSION = "2026-10-09"
# Standard text/audio token prices per 1M, from official model pages. No
# per-minute diarization assumption: duration-only usage stays unavailable.
RATES = {
    "gpt-6-luna": (Decimal("0.10"), Decimal("0.50"), Decimal("0.01")),
    "gpt-4.1-mini": (Decimal("0.40"), Decimal("1.60"), Decimal("0.10")),
    "gpt-4o-transcribe-diarize": (Decimal("2.50"), Decimal("10.00"), None),
}


def _usage_dict(response):
    raw = getattr(response, "usage", None)
    if raw is None:
        return {}
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump(exclude_none=True)
    if not isinstance(raw, dict):
        return {}
    allowed = {"type", "seconds", "input_tokens", "output_tokens", "total_tokens"}
    result = {key: raw[key] for key in allowed if key in raw}
    details = raw.get("input_token_details") or raw.get("input_tokens_details")
    if isinstance(details, dict):
        result["input_token_details"] = {
            key: details[key] for key in ("audio_tokens", "text_tokens", "cached_tokens")
            if key in details
        }
    return result


def estimate_cost(model, usage):
    rates = RATES.get(model)
    incoming, outgoing = usage.get("input_tokens"), usage.get("output_tokens")
    if rates is None or not isinstance(incoming, int) or not isinstance(outgoing, int):
        return None, "unavailable", ""
    if incoming < 0 or outgoing < 0:
        return None, "unavailable", ""
    input_rate, output_rate, cached_rate = rates
    # Luna's long-context tier uses higher input/output prices. We only have
    # aggregate tokens, so this remains an estimate, not invoice reconciliation.
    if model == "gpt-6-luna" and incoming > 272_000:
        input_rate *= 2
        output_rate *= Decimal("1.5")
        if cached_rate is not None:
            cached_rate *= 2
    cached = usage.get("input_token_details", {}).get("cached_tokens", 0)
    if not isinstance(cached, int) or cached < 0 or cached > incoming or cached_rate is None:
        cached = 0
    amount = (
        Decimal(incoming - cached) * input_rate
        + Decimal(cached) * (cached_rate or input_rate)
        + Decimal(outgoing) * output_rate
    ) / Decimal(1_000_000)
    return amount.quantize(Decimal("0.00000001")), "estimated", PRICING_VERSION


def record_ai_attempt(
    *, context, provider_id, model, usage=None, outcome="success",
    estimated_usd=None, estimate_status="unavailable", pricing_version="",
    request_id="", error_type="", source_label="",
):
    """Provider-neutral ledger boundary; callers pass only sanitized usage units."""
    if not context:
        return
    if not isinstance(provider_id, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{1,39}", provider_id):
        raise ValueError("Invalid AI provider identifier")
    raw = usage if isinstance(usage, dict) else {}
    usage = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = raw.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            usage[key] = value
    seconds = raw.get("seconds")
    if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and seconds >= 0:
        usage["seconds"] = seconds
    if raw.get("type") in ("duration", "tokens"):
        usage["type"] = raw["type"]
    details = raw.get("input_token_details")
    if isinstance(details, dict):
        usage["input_token_details"] = {
            key: value for key in ("audio_tokens", "text_tokens", "cached_tokens")
            if isinstance((value := details.get(key)), int)
            and not isinstance(value, bool) and value >= 0
        }
    tokens = {}
    for name in ("input_tokens", "output_tokens", "total_tokens"):
        value = usage.get(name)
        tokens[name] = (
            value if isinstance(value, int) and not isinstance(value, bool) and value >= 0
            else None
        )
    if (tokens["total_tokens"] is None and tokens["input_tokens"] is not None
            and tokens["output_tokens"] is not None):
        tokens["total_tokens"] = tokens["input_tokens"] + tokens["output_tokens"]
    if outcome != "success":
        estimated_usd, estimate_status, pricing_version = None, "unavailable", ""
    try:
        with transaction.atomic():
            AIUsageEvent.objects.create(
                sector_id=context["sector_id"], requested_by_id=context["user_id"],
                meeting_id=context["meeting_id"], job_id=context.get("job_id"),
                operation=context["operation"], provider_id=provider_id, model=model,
                key_version=context["key_version"], request_id=str(request_id)[:100],
                prompt_version=(context.get("prompt_version")
                                if type(context.get("prompt_version")) is int else None),
                prompt_fingerprint=(fingerprint(context["system_prompt"])
                                    if isinstance(context.get("system_prompt"), str) else ""),
                outcome=outcome, error_type=error_type[:80],
                source_label=source_label[:100], usage=usage,
                **tokens,
                estimated_usd=estimated_usd, estimate_status=estimate_status,
                pricing_version=pricing_version,
            )
    except IntegrityError:
        # Duplicate request ID from a repeated callback must not be billed twice locally.
        logger.warning("Duplicate provider request ID omitted from usage ledger")
    except Exception:
        logger.exception("Could not persist AI usage event")


def record_openai_usage(response, context, model, source_label=""):
    """Best effort: accounting failure must not corrupt successful AI results."""
    usage = _usage_dict(response)
    amount, status, version = estimate_cost(model, usage)
    record_ai_attempt(
        context=context, provider_id="openai", model=model, usage=usage,
        estimated_usd=amount, estimate_status=status, pricing_version=version,
        request_id=getattr(response, "_request_id", "") or "", source_label=source_label,
    )


def record_openai_failure(error, context, model, source_label=""):
    """Record an attempted external call, without assuming a failed request is free.

    Never persist the exception message: it can contain a URL, credential or payload.
    """
    record_ai_attempt(
        context=context, provider_id="openai", model=model, outcome="failed",
        request_id=getattr(error, "request_id", "") or "",
        error_type=type(error).__name__, source_label=source_label,
    )


def tracked_openai_call(call, context, model, source_label=""):
    """One ledger event per SDK attempt (SDK retries are disabled in _client)."""
    try:
        response = call()
    except Exception as exc:
        record_openai_failure(exc, context, model, source_label)
        raise
    record_openai_usage(response, context, model, source_label)
    return response
