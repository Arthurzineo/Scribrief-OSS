"""Removing external identity placeholders must not enable local password login."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_local_only_migration_rejects_external_rows_and_preserves_local_accounts():
    before = ("accounts", "0009_usermembership_bootstrap_local_only")
    after = (
        "accounts", "0010_remove_usermembership_unique_nonempty_external_identity_and_more",
    )
    executor = MigrationExecutor(connection)
    executor.migrate([before])
    old = executor.loader.project_state([before]).apps
    User = old.get_model("auth", "User")
    Sector = old.get_model("accounts", "Sector")
    Membership = old.get_model("accounts", "UserMembership")
    sector = Sector.objects.create(name="Migração", slug="migracao-local")
    local_user = User.objects.create(username="local-migration-test")
    local = Membership.objects.create(
        user=local_user, sector=sector, auth_source="local", external_id="stale-external-id",
    )
    external_user = User.objects.create(username="external-migration-test")
    external = Membership.objects.create(
        user=external_user, sector=sector, auth_source="ldap", external_id="external-123",
    )
    try:
        with pytest.raises(RuntimeError, match="vínculos de autenticação externa"):
            MigrationExecutor(connection).migrate([after])
        external.delete()
        with pytest.raises(RuntimeError, match="vínculos de autenticação externa"):
            MigrationExecutor(connection).migrate([after])
        local.external_id = ""
        local.save(update_fields=["external_id"])
        MigrationExecutor(connection).migrate([after])
        current = MigrationExecutor(connection).loader.project_state([after]).apps
        NewMembership = current.get_model("accounts", "UserMembership")
        assert NewMembership.objects.filter(user_id=local_user.pk).exists()
        assert "auth_source" not in {field.name for field in NewMembership._meta.fields}
        assert "external_id" not in {field.name for field in NewMembership._meta.fields}
    finally:
        # No external row should be left if an assertion fails before the second migration.
        if after not in MigrationExecutor(connection).loader.applied_migrations:
            Membership.objects.filter(pk=external.pk).delete()
            Membership.objects.filter(pk=local.pk).update(external_id="")
            MigrationExecutor(connection).migrate([after])
