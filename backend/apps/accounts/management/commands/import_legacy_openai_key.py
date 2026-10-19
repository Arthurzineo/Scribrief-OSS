"""One-time, explicit import of the old environment key into the legacy sector."""

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Sector, SectorOpenAIKey
from apps.accounts.secrets import save_sector_key, sector_api_key


class Command(BaseCommand):
    help = "Import OPENAI_API_KEY once into the encrypted legacy-sector credential."

    def handle(self, *args, **options):
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise CommandError("OPENAI_API_KEY is not set")
        sector = Sector.objects.filter(slug="legado").first()
        if sector is None:
            raise CommandError("Legacy sector does not exist; run migrations first")
        with transaction.atomic():
            if SectorOpenAIKey.objects.select_for_update().filter(
                sector=sector, provider_id="openai"
            ).exists():
                raise CommandError("Legacy sector already has a key; refusing to overwrite")
            save_sector_key(sector, key)
            if sector_api_key(sector.pk) != key:
                raise CommandError("Encrypted key verification failed")
        self.stdout.write(self.style.SUCCESS("Legacy sector key imported and verified."))
