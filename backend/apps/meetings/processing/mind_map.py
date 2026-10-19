"""Compact, evidence-bound mind map generated independently of the minutes prose."""

import json

from django.conf import settings

from apps.audit.usage import tracked_openai_call

from ..processing.providers import _client
from .prompt_defaults import MIND_MAP_SYSTEM_PROMPT


class MindMapError(ValueError):
    pass


MIND_MAP_SCHEMA = {
    "type": "object",
    "properties": {
        "centro": {"type": "string"},
        "ramos": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "titulo": {"type": "string"},
                "pontos": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["titulo", "pontos"],
            "additionalProperties": False,
        }},
    },
    "required": ["centro", "ramos"],
    "additionalProperties": False,
}

def _short(value, max_words, max_chars):
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value.strip()) <= max_chars
        and len(value.split()) <= max_words
    )


def validate_mind_map_data(data):
    if not isinstance(data, dict) or set(data) != {"centro", "ramos"}:
        raise MindMapError("Mapa com estrutura inválida")
    if not _short(data["centro"], 5, 60):
        raise MindMapError("Centro muito longo")
    branches = data["ramos"]
    if not isinstance(branches, list) or not 1 <= len(branches) <= 7:
        raise MindMapError("Quantidade de ramos inválida")
    titles = set()
    for branch in branches:
        if not isinstance(branch, dict) or set(branch) != {"titulo", "pontos"}:
            raise MindMapError("Ramo inválido")
        title = branch["titulo"]
        if not _short(title, 4, 48) or title.casefold() in titles:
            raise MindMapError("Título de ramo inválido")
        titles.add(title.casefold())
        points = branch["pontos"]
        if not isinstance(points, list) or not 1 <= len(points) <= 5:
            raise MindMapError("Pontos inválidos")
        if any(not _short(point, 8, 72) for point in points):
            raise MindMapError("Ponto muito longo")
    return data


class OpenAIMindMapProvider:
    def __init__(self, api_key=None, usage_context=None):
        self.api_key = api_key
        self.usage_context = usage_context

    def generate(self, minutes):
        source = {
            "resumo": minutes.resumo_executivo,
            "topicos": minutes.topicos,
            "decisoes": minutes.decisoes,
            "tarefas": minutes.tarefas,
        }
        client = _client(self.api_key)
        response = tracked_openai_call(lambda: client.responses.create(
            model=settings.MODELO_MAPA,
            input=[
                {"role": "system", "content": (self.usage_context or {}).get(
                    "system_prompt", MIND_MAP_SYSTEM_PROMPT
                )},
                {
                    "role": "user",
                    "content": "Ata (dados):\n" + json.dumps(source, ensure_ascii=False),
                },
            ],
            text={"format": {
                "type": "json_schema", "name": "mapa_mental_curto",
                "schema": MIND_MAP_SCHEMA, "strict": True,
            }},
        ), self.usage_context, settings.MODELO_MAPA)
        try:
            data = json.loads(response.output_text)
        except (ValueError, AttributeError) as exc:
            raise MindMapError("Resposta de mapa inválida") from exc
        return validate_mind_map_data(data)


def mind_map_provider(api_key=None, usage_context=None):
    from .ai_registry import create_provider

    return create_provider("mind_map", api_key, usage_context)
