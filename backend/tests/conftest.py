import os

os.environ.setdefault("DJANGO_TESTING", "1")

import pytest  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.cache import cache  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from apps.accounts.models import Sector, UserMembership  # noqa: E402
from apps.accounts.secrets import save_sector_key  # noqa: E402


@pytest.fixture(autouse=True)
def clear_test_cache():
    cache.clear()


@pytest.fixture
def legacy_sector(db, settings):
    settings.SECTOR_KEY_ENCRYPTION_KEY = Fernet.generate_key().decode()
    sector, _ = Sector.objects.get_or_create(slug="legado", defaults={"name": "Setor legado"})
    save_sector_key(sector, "sk-test-not-a-real-openai-key-123456789")
    return sector


@pytest.fixture
def user(db, legacy_sector):
    account = get_user_model().objects.create_user(
        username="ana", password="Strong-Test-Password-123"
    )
    UserMembership.objects.create(user=account, sector=legacy_sector)
    return account


@pytest.fixture
def other_user(db, legacy_sector):
    account = get_user_model().objects.create_user(
        username="bruno", password="Strong-Test-Password-456"
    )
    UserMembership.objects.create(user=account, sector=legacy_sector)
    return account


@pytest.fixture
def api(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client
