"""Explicit, dry-run-by-default audit retention command for an operator."""

from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.audit.models import AuditEvent, HealthSample, SystemEvent
from apps.audit.retention import prune_audit_before


class Command(BaseCommand):
    help = "Count or delete audit/system events and health samples; requires --confirm."

    def add_arguments(self, parser):
        parser.add_argument("--before", required=True, help="Exclusive cutoff, YYYY-MM-DD")
        parser.add_argument("--confirm", action="store_true", help="Actually delete old events")

    def handle(self, *args, **options):
        date = parse_date(options["before"])
        if date is None:
            raise CommandError("--before must be YYYY-MM-DD")
        if date > timezone.localdate() - timedelta(days=90):
            raise CommandError("Minimum retention is 90 days")
        cutoff = timezone.make_aware(datetime.combine(date, time.min))
        qs = AuditEvent.objects.filter(created_at__lt=cutoff)
        count = qs.count()
        system_count = SystemEvent.objects.filter(created_at__lt=cutoff).count()
        health_count = HealthSample.objects.filter(created_at__lt=cutoff).count()
        if not options["confirm"]:
            self.stdout.write(
                f"DRY RUN: {count} audit events, {system_count} system events "
                f"and {health_count} health samples "
                f"before {date.isoformat()}"
            )
            return
        result = prune_audit_before(cutoff)
        if result["status"] == "busy":
            raise CommandError("An audit-retention run is already in progress")
        self.stdout.write(
            f"Deleted {result['deleted']} audit events and "
            f"{result['system_deleted']} system events and "
            f"{result['health_deleted']} health samples before {date.isoformat()}"
        )
        if result["remaining"] or result["system_remaining"] or result["health_remaining"]:
            self.stdout.write(self.style.WARNING("Backlog remains; run again later."))
