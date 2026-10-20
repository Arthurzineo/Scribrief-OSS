"""One-time local-only initial administrator for the OSS beta installer."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.initial_access import unsafe_bootstrap_bind
from apps.accounts.models import Sector, UserMembership


class Command(BaseCommand):
    help = "Create the first local ADMIN account; never reset an existing installation."

    def add_arguments(self, parser):
        parser.add_argument("--skip-create", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        user_model = get_user_model()
        pending = UserMembership.objects.filter(
            must_change_password=True, bootstrap_local_only=True,
        ).exists()
        create = not options["skip_create"] and not user_model.objects.exists()
        if pending or create:
            if label := unsafe_bootstrap_bind():
                raise CommandError(
                    f"Conta inicial pendente: {label} deve permanecer em loopback "
                    "até a troca da senha no primeiro login."
                )
        if not create:
            self.stdout.write("Contas existentes preservadas; nenhum usuário demo criado.")
            return
        sector = Sector.objects.create(name="Administração", slug="administracao")
        admin = user_model.objects.create_superuser(username="ADMIN", password="ADMIN123")
        UserMembership.objects.create(
            user=admin, sector=sector, must_change_password=True, bootstrap_local_only=True,
        )
        self.stdout.write(
            "Conta ADMIN criada para acesso local. Troque a senha no primeiro login "
            "antes de liberar qualquer porta na LAN. Nenhum usuário demo foi criado."
        )
