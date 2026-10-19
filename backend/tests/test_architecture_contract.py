"""Architecture guardrails for data, Celery, API documentation and app imports."""

import ast
from pathlib import Path

from django.db import models

from apps.accounts.models import Sector, SectorAICredential, UserMembership
from apps.accounts.urls import urlpatterns as account_urlpatterns
from apps.audit.models import AIUsageEvent, AuditEvent
from apps.meetings.models import (
    Meeting,
    Minutes,
    ProcessingJob,
    Segment,
    Speaker,
    SpeakerAnalysis,
    TranscriptionChunk,
)
from apps.meetings.tasks import (
    analyze_speaker_reconciliation,
    analyze_transcription_corrections,
    generate_mind_map,
    generate_minutes,
    process_meeting,
)
from config.openapi import AUTH_PATHS


def test_model_tables_and_file_only_media_contract():
    expected = {
        Sector: "accounts_sector",
        UserMembership: "accounts_usermembership",
        SectorAICredential: "accounts_sectoraicredential",
        Meeting: "meetings_meeting",
        ProcessingJob: "meetings_processingjob",
        Speaker: "meetings_speaker",
        Segment: "meetings_segment",
        TranscriptionChunk: "meetings_transcriptionchunk",
        SpeakerAnalysis: "meetings_speakeranalysis",
        Minutes: "meetings_minutes",
        AuditEvent: "audit_auditevent",
        AIUsageEvent: "audit_aiusageevent",
    }
    for model, table in expected.items():
        assert model._meta.db_table == table
        assert not any(
            isinstance(field, (models.BinaryField, models.FileField))
            for field in model._meta.fields
        )


def test_celery_task_names_survive_module_refactor():
    assert process_meeting.name == "meetings.process_meeting"
    assert generate_minutes.name == "meetings.generate_minutes"
    assert generate_mind_map.name == "meetings.generate_mind_map"
    assert analyze_speaker_reconciliation.name == "meetings.analyze_speaker_reconciliation"
    assert analyze_transcription_corrections.name == "meetings.analyze_transcription_corrections"


def test_plain_django_account_routes_are_documented_in_openapi():
    expected = {f"/api/v1/{route.pattern}" for route in account_urlpatterns}
    assert expected <= AUTH_PATHS.keys()


def test_cross_app_imports_keep_current_dependency_direction():
    """A new cross-app import should require an explicit architecture review."""
    allowed = {
        "accounts": {"audit"},
        "audit": set(),
        "meetings": {"accounts", "audit"},
        "admin_panel": {"accounts", "audit", "meetings"},
    }
    unexpected = []
    root = Path(__file__).resolve().parents[1] / "apps"
    for path in root.rglob("*.py"):
        if "migrations" in path.parts or "management" in path.parts:
            continue
        owner = path.relative_to(root).parts[0]
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] if node.level == 0 else []
            else:
                continue
            for name in names:
                if not name.startswith("apps."):
                    continue
                target = name.split(".")[1]
                if target != owner and target not in allowed[owner]:
                    unexpected.append((str(path.relative_to(root)), target))
    assert unexpected == []
