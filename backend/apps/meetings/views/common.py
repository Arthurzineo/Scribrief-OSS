
from django.core.exceptions import ImproperlyConfigured

from apps.accounts.secrets import SectorKeyUnavailable, sector_credential

from ..processing.ai_registry import (
    AIProviderConfigurationError,
    capability_for_operation,
    selected_provider,
)
from ..services import (
    Conflict,
)


def _speaker_analysis_payload(meeting, analysis):
    active_codes = set(
        meeting.speakers.filter(merged_into__isnull=True).values_list("code", flat=True)
    )
    groups = [] if analysis is None else [
        [code for code in group if code in active_codes]
        for group in analysis.groups
    ]
    groups = [group for group in groups if len(group) >= 2]
    return {
        "job_id": str(analysis.job_id) if analysis and analysis.job_id else None,
        "meeting_id": str(meeting.id),
        "version": analysis.version if analysis else meeting.transcription_version,
        "status": analysis.status if analysis else "none",
        "uses": analysis.uses if analysis else 0,
        "remaining": 2 - analysis.uses if analysis else 2,
        "groups": groups,
        "caution": analysis.caution if analysis else False,
        "sample_times": analysis.sample_times if analysis else {},
        "message": analysis.message if analysis else "",
    }


def _require_sector_key(sector_id, operation="transcription_chunk"):
    try:
        provider_id = selected_provider(capability_for_operation(operation))
        sector_credential(sector_id, provider_id)
    except SectorKeyUnavailable as exc:
        raise Conflict("Setor sem credencial do provedor de IA configurada.") from exc
    except AIProviderConfigurationError as exc:
        raise Conflict("Provedor de IA indisponível para esta operação.") from exc
    except ImproperlyConfigured as exc:
        raise Conflict("Credencial setorial temporariamente indisponível.") from exc
