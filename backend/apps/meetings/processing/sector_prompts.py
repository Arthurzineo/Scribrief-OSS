"""Resolve a sector's effective prompt at job execution time."""

from apps.accounts.models import SectorAIPrompt

from .prompt_defaults import SYSTEM_PROMPT_DEFAULTS


def effective_prompt(sector_id, kind):
    if kind not in SYSTEM_PROMPT_DEFAULTS:
        raise ValueError("Unsupported system prompt kind")
    override = SectorAIPrompt.objects.filter(sector_id=sector_id, kind=kind).first()
    if override is None:
        return SYSTEM_PROMPT_DEFAULTS[kind], 0
    return override.text, override.version
