"""Trusted adapter registry: vendor choice varies; meeting policy does not."""

from django.conf import settings
from django.utils.module_loading import import_string


class AIProviderConfigurationError(RuntimeError):
    pass


# Registration is code-reviewed, never a dotted import path supplied by a request.
# Another vendor may implement only the capabilities it actually supports.
AI_ADAPTERS = {
    "openai": {
        "transcription": "apps.meetings.processing.providers.OpenAITranscriptionProvider",
        "minutes": "apps.meetings.processing.providers.OpenAIMinutesProvider",
        "mind_map": "apps.meetings.processing.mind_map.OpenAIMindMapProvider",
        "correction": "apps.meetings.processing.corrections.OpenAICorrectionProvider",
    },
}

CAPABILITY_METHODS = {
    "transcription": "transcribe",
    "minutes": "generate",
    "mind_map": "generate",
    "correction": "suggest",
}

OPERATION_CAPABILITIES = {
    "transcription_chunk": "transcription",
    "speaker_reconciliation": "transcription",
    "minutes": "minutes",
    "mind_map": "mind_map",
    "correction": "correction",
}


def capability_for_operation(operation):
    try:
        return OPERATION_CAPABILITIES[operation]
    except KeyError as exc:
        raise AIProviderConfigurationError("Operação de IA desconhecida") from exc


def selected_provider(capability):
    if capability not in CAPABILITY_METHODS:
        raise AIProviderConfigurationError("Capacidade de IA desconhecida")
    provider_id = getattr(settings, f"AI_PROVIDER_{capability.upper()}", "openai")
    if not isinstance(provider_id, str) or capability not in AI_ADAPTERS.get(provider_id, {}):
        raise AIProviderConfigurationError("Provedor de IA não suporta esta capacidade")
    return provider_id


def create_provider(capability, credential, usage_context=None):
    provider_id = selected_provider(capability)
    adapter = import_string(AI_ADAPTERS[provider_id][capability])
    instance = adapter(credential, usage_context)
    if not callable(getattr(instance, CAPABILITY_METHODS[capability], None)):
        raise AIProviderConfigurationError("Adaptador de IA não implementa o contrato")
    return instance
