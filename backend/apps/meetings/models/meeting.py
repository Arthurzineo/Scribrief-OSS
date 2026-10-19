import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models

DELETION_GRACE_PERIOD = timedelta(days=3)


class MeetingStatus(models.TextChoices):
    ENVIADO = "enviado", "Enviado"
    EXTRAINDO_AUDIO = "extraindo_audio", "Extraindo áudio"
    TRANSCREVENDO = "transcrevendo", "Transcrevendo"
    TRANSCRITO = "transcrito", "Transcrito"
    GERANDO_ATA = "gerando_ata", "Gerando ata"
    ATA_PRONTA = "ata_pronta", "Ata pronta"
    ERRO = "erro", "Erro"

class Meeting(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="meetings"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_meetings"
    )
    sector = models.ForeignKey(
        "accounts.Sector", on_delete=models.PROTECT, related_name="meetings"
    )
    shared_with_sector = models.BooleanField(default=False)
    access_version = models.PositiveIntegerField(default=0)
    title = models.CharField(max_length=200)
    meeting_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=24, choices=MeetingStatus.choices, default=MeetingStatus.ENVIADO
    )
    job_id = models.UUIDField(null=True, blank=True)
    job_claimed = models.BooleanField(default=False)
    job_started_at = models.DateTimeField(null=True, blank=True)
    original_name = models.CharField(max_length=255, blank=True)
    original_path = models.CharField(max_length=500, blank=True)
    audio_path = models.CharField(max_length=500, blank=True)
    consent_confirmed_at = models.DateTimeField(null=True, blank=True)
    staged_at = models.DateTimeField(null=True, blank=True, db_index=True)
    transcription_version = models.PositiveIntegerField(default=0)
    minutes_version = models.PositiveIntegerField(default=0)
    minutes_stale = models.BooleanField(default=False)
    error_code = models.CharField(max_length=60, blank=True)
    error_message = models.CharField(max_length=240, blank=True)
    deletion_requested_at = models.DateTimeField(null=True, blank=True, db_index=True)
    purge_attempts = models.PositiveIntegerField(default=0)
    purge_error_code = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["owner", "status", "created_at"])]

    @property
    def deletion_due_at(self):
        return (
            self.deletion_requested_at + DELETION_GRACE_PERIOD
            if self.deletion_requested_at else None
        )

    def save(self, *args, **kwargs):
        if self._state.adding:
            from django.core.exceptions import ValidationError

            from apps.accounts.models import UserMembership

            membership = UserMembership.objects.filter(user_id=self.owner_id).first()
            if membership is None:
                raise ValidationError("O proprietário deve pertencer a um setor.")
            if self.created_by_id is None:
                self.created_by_id = self.owner_id
            if self.sector_id is None:
                self.sector_id = membership.sector_id
            if self.sector_id != membership.sector_id:
                raise ValidationError("O proprietário deve pertencer ao setor da reunião.")
        super().save(*args, **kwargs)
