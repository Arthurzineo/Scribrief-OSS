"""Create synthetic demo data without calling the OpenAI API."""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Sector, UserMembership
from apps.meetings.exports import export_minutes, export_transcript
from apps.meetings.models import Meeting, MeetingStatus, Minutes, Segment, Speaker


class Command(BaseCommand):
    help = "Create synthetic demo user/meeting. Requires DEMO_SEED_ALLOWED=true and DEMO_PASSWORD."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo")

    def handle(self, *args, **options):
        if os.getenv("DEMO_SEED_ALLOWED", "false").lower() != "true":
            raise CommandError("Set DEMO_SEED_ALLOWED=true explicitly")
        password = os.getenv("DEMO_PASSWORD", "")
        if len(password) < 12:
            raise CommandError("DEMO_PASSWORD must have at least 12 characters")
        username = options["username"]
        with transaction.atomic():
            user, created = get_user_model().objects.get_or_create(username=username)
            if created:
                user.set_password(password)
                user.save(update_fields=["password"])
            sector, _ = Sector.objects.get_or_create(
                slug="legado", defaults={"name": "Setor legado"}
            )
            UserMembership.objects.get_or_create(user=user, defaults={"sector": sector})
            meeting, created = Meeting.objects.get_or_create(
                owner=user,
                title="DEMO — reunião de exemplo",
                defaults={
                    "status": MeetingStatus.ATA_PRONTA,
                    "transcription_version": 1,
                    "minutes_version": 1,
                },
            )
            if created:
                ana = Speaker.objects.create(meeting=meeting, code="A", name="Ana")
                bruno = Speaker.objects.create(meeting=meeting, code="B", name="Bruno")
                Segment.objects.create(
                    meeting=meeting,
                    speaker=ana,
                    start_ms=0,
                    end_ms=3000,
                    text="Vamos revisar o cronograma do projeto.",
                    order=0,
                )
                Segment.objects.create(
                    meeting=meeting,
                    speaker=bruno,
                    start_ms=3100,
                    end_ms=6000,
                    text="Concordo. Entrego a primeira versão na sexta-feira.",
                    order=1,
                )
                Minutes.objects.create(
                    meeting=meeting,
                    resumo_executivo="Equipe revisou o cronograma.",
                    topicos=[
                        {
                            "titulo": "Cronograma e entregas",
                            "comentario": "A equipe revisou o cronograma. Bruno se comprometeu "
                            "a entregar a primeira versão na sexta-feira.",
                        }
                    ],
                    decisoes=["Manter o cronograma proposto."],
                    tarefas=[
                        {
                            "descricao": "Entregar primeira versão",
                            "responsavel": "Bruno",
                            "prazo": "sexta-feira",
                        }
                    ],
                )
        export_transcript(meeting)
        export_minutes(meeting)
        self.stdout.write(
            self.style.SUCCESS(f"Demo ready for username={username}, meeting={meeting.id}")
        )
