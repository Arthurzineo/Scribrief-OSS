"""Fail deployment checks when a selected AI adapter is missing or incomplete."""

from django.core.checks import Error, register
from django.utils.module_loading import import_string

from .processing.ai_registry import (
    AI_ADAPTERS,
    CAPABILITY_METHODS,
    AIProviderConfigurationError,
    selected_provider,
)


@register()
def check_ai_providers(app_configs, **kwargs):
    issues = []
    for capability, method in CAPABILITY_METHODS.items():
        try:
            provider_id = selected_provider(capability)
            adapter = import_string(AI_ADAPTERS[provider_id][capability])
            if not callable(getattr(adapter, method, None)):
                raise AIProviderConfigurationError("Método obrigatório ausente")
        except (AIProviderConfigurationError, ImportError, AttributeError, ValueError):
            issues.append(Error(
                f"Adaptador de IA inválido para {capability}.", id="meetings.E001"
            ))
    return issues
