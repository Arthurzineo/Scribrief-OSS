from django.conf import settings
from django.db import models

from .meeting import Meeting


class Minutes(models.Model):
    meeting = models.OneToOneField(Meeting, on_delete=models.CASCADE, related_name="minutes")
    resumo_executivo = models.TextField()
    topicos = models.JSONField(default=list)
    decisoes = models.JSONField(default=list)
    tarefas = models.JSONField(default=list)
    participantes = models.JSONField(default=list)
    mind_map = models.JSONField(default=dict)
    mind_map_version = models.PositiveIntegerField(default=0)
    mind_map_status = models.CharField(max_length=12, default="none")
    mind_map_job_id = models.UUIDField(null=True, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    human_edited = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reviewed_minutes",
    )
    reviewer_name = models.CharField(max_length=150, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
