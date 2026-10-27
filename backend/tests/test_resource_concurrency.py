"""Real PostgreSQL row-lock tests; never claim SQLite proves serialization."""

import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from django.db import close_old_connections, connection, connections, transaction

from apps.accounts.services.ai_budget import AIBudgetExceeded, reserve_ai_call
from apps.audit.models import AIBudgetEntry
from apps.meetings.models import Meeting, UploadGate, UploadLease
from apps.meetings.services.upload_capacity import UploadCapacityExceeded, acquire_upload

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL locks required"),
]


def _wait_for_both_lock_waiters(label):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE application_name = %s AND wait_event_type = 'Lock'", [label],
            )
            if cursor.fetchone()[0] == 2:
                return
        time.sleep(0.02)
    pytest.fail("The two independent connections never overlapped at the row lock")


def _run_pair(lock, action, label):
    barrier = Barrier(3)

    def run(index):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET application_name = %s", [label])
            barrier.wait(timeout=10)
            try:
                action(index)
                return "accepted"
            except (AIBudgetExceeded, UploadCapacityExceeded):
                return "denied"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        with transaction.atomic():
            lock()
            futures = [pool.submit(run, index) for index in (0, 1)]
            barrier.wait(timeout=10)
            _wait_for_both_lock_waiters(label)
        return sorted(future.result(timeout=15) for future in futures)


def test_budget_race_admits_only_one_reservation(user):
    sector = user.membership.sector
    sector.monthly_ai_budget_usd = Decimal("0.10")
    sector.save(update_fields=["monthly_ai_budget_usd"])
    meeting = Meeting.objects.create(owner=user, title="Corrida budget")
    context = {"sector_id": sector.pk, "user_id": user.pk,
               "meeting_id": meeting.pk, "operation": "minutes", "key_version": 1}
    results = _run_pair(
        lambda: type(sector).objects.select_for_update().get(pk=sector.pk),
        lambda _: reserve_ai_call(context, Decimal("0.06")), "p057-budget-race",
    )
    assert results == ["accepted", "denied"]
    assert AIBudgetEntry.objects.count() == 1


def test_upload_race_keeps_capacity_for_other_http_workers(user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    meetings = [Meeting.objects.create(owner=user, title=f"Corrida {i}") for i in range(2)]
    UploadGate.objects.get_or_create(pk=1)
    results = _run_pair(
        lambda: UploadGate.objects.select_for_update().get(pk=1),
        lambda index: acquire_upload(meetings[index].pk, user, 100), "p057-upload-race",
    )
    assert results == ["accepted", "denied"]
    assert UploadLease.objects.count() == 1
