"""Verify that adding sectors preserves legacy ownership and media paths."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_legacy_meeting_backfill_preserves_file_paths():
    before = ("meetings", "0012_backfill_speaker_analysis_uses")
    after = ("meetings", "0015_alter_meeting_created_by_alter_meeting_sector")
    accounts_at_backfill = ("accounts", "0001_initial")
    executor = MigrationExecutor(connection)
    executor.migrate([before, accounts_at_backfill])
    old = executor.loader.project_state([before, accounts_at_backfill]).apps
    User = old.get_model("auth", "User")
    Meeting = old.get_model("meetings", "Meeting")
    owner = User.objects.create(username="legacy-migration-test")
    meeting = Meeting.objects.create(
        owner_id=owner.pk,
        title="Reunião antiga",
        original_path="private/legacy/original.mp4",
        audio_path="private/legacy/audio.mp3",
    )
    executor = MigrationExecutor(connection)
    try:
        executor.migrate([after, accounts_at_backfill])
        migrated = executor.loader.project_state([after, accounts_at_backfill]).apps
        NewMeeting = migrated.get_model("meetings", "Meeting")
        current = NewMeeting.objects.get(pk=meeting.pk)
        assert current.owner_id == owner.pk
        assert current.created_by_id == owner.pk
        assert current.sector.slug == "legado"
        assert current.original_path == "private/legacy/original.mp4"
        assert current.audio_path == "private/legacy/audio.mp3"
        Membership = migrated.get_model("accounts", "UserMembership")
        assert Membership.objects.get(user_id=owner.pk).sector_id == current.sector_id
    finally:
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        )
