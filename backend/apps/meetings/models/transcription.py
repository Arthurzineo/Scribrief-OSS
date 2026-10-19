from django.core.validators import MinValueValidator
from django.db import models

from .meeting import Meeting


class Speaker(models.Model):
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="speakers")
    code = models.CharField(max_length=16)
    name = models.CharField(max_length=100)
    merged_into = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["meeting", "code"], name="unique_speaker_per_meeting")
        ]
        ordering = ["code"]

class Segment(models.Model):
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="segments")
    speaker = models.ForeignKey(Speaker, on_delete=models.PROTECT, related_name="segments")
    start_ms = models.PositiveIntegerField(validators=[MinValueValidator(0)])
    end_ms = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    text = models.TextField()
    # Frozen at AI publication. Existing pre-migration rows are explicitly a
    # legacy baseline, because earlier human edits cannot be reconstructed.
    original_text = models.TextField(blank=True, default="")
    original_start_ms = models.PositiveIntegerField(null=True, blank=True)
    original_end_ms = models.PositiveIntegerField(null=True, blank=True)
    original_speaker_code = models.CharField(max_length=16, blank=True, default="")
    original_source = models.CharField(max_length=24, default="unverified")
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["meeting", "order"], name="unique_segment_order")
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.end_ms <= self.start_ms:
            raise ValidationError("end_ms must exceed start_ms")
        if self.speaker_id and self.speaker.meeting_id != self.meeting_id:
            raise ValidationError("speaker must belong to same meeting")

class TranscriptionChunk(models.Model):
    """Private durable checkpoint, invisible until the full transcript is committed."""

    meeting = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="transcription_chunks"
    )
    index = models.PositiveIntegerField()
    offset_ms = models.PositiveBigIntegerField()
    audio_sha256 = models.CharField(max_length=64)
    provider_id = models.CharField(max_length=40, default="openai")
    model = models.CharField(max_length=100)
    language = models.CharField(max_length=16, blank=True)
    segments = models.JSONField(default=list)
    completed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["meeting", "index"], name="unique_chunk_per_meeting")
        ]
        ordering = ["index"]
