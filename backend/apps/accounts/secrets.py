"""Encrypted sector/provider credentials; Fernet master key stays outside the DB."""

import re

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction

from .models import Sector, SectorAICredential


class SectorKeyUnavailable(RuntimeError):
    pass


def _cipher():
    raw = settings.SECTOR_KEY_ENCRYPTION_KEY
    if not raw:
        raise ImproperlyConfigured("SECTOR_KEY_ENCRYPTION_KEY is required")
    try:
        return Fernet(raw.encode())
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured("Invalid sector encryption key") from exc


@transaction.atomic
def save_sector_credential(sector, provider_id, plaintext):
    if not isinstance(provider_id, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{1,39}", provider_id):
        raise ValueError("Invalid AI provider identifier")
    if not isinstance(plaintext, str) or not 8 <= len(plaintext) <= 500:
        raise ValueError("Invalid AI credential length")
    # Serialize initial creation and rotations on the owning sector row.
    Sector.objects.select_for_update().get(pk=sector.pk)
    ciphertext = _cipher().encrypt(plaintext.encode()).decode()
    credential, created = SectorAICredential.objects.get_or_create(
        sector=sector, provider_id=provider_id, defaults={"ciphertext": ciphertext}
    )
    if not created:
        credential.ciphertext = ciphertext
        credential.version += 1
        credential.save(update_fields=["ciphertext", "version", "updated_at"])
    return credential


def save_sector_key(sector, plaintext):
    """Compatibility helper for the currently configured OpenAI provider."""
    if not isinstance(plaintext, str) or len(plaintext) < 20:
        raise ValueError("Invalid OpenAI key length")
    return save_sector_credential(sector, "openai", plaintext)


def sector_credential(sector_id, provider_id="openai"):
    credential = SectorAICredential.objects.select_related("sector").filter(
        sector_id=sector_id, provider_id=provider_id, sector__is_active=True
    ).first()
    if credential is None:
        raise SectorKeyUnavailable("Setor sem credencial do provedor configurada")
    try:
        return _cipher().decrypt(credential.ciphertext.encode()).decode(), credential.version
    except InvalidToken as exc:
        raise SectorKeyUnavailable("Chave setorial indisponível") from exc


def sector_api_key(sector_id):
    return sector_credential(sector_id)[0]
