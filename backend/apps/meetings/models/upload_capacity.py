"""Database admission leases shared by every HTTP process (never a local semaphore)."""

import uuid

from django.conf import settings
from django.db import models


class UploadGate(models.Model):
    # The single seeded row is locked only while admitting/releasing a request.
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)


class UploadLease(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Snapshot, not a cascading FK: deleting the draft must not free the slot
    # while its multipart body is still being received by another HTTP worker.
    meeting_id = models.UUIDField(unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reserved_bytes = models.PositiveBigIntegerField()
    expires_at = models.DateTimeField(db_index=True)
