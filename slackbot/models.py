"""Database models that track Slack summaries."""
from __future__ import annotations

from django.db import models


class ConversationSummary(models.Model):
    """Stores the latest summary for a Slack thread or channel."""

    class TargetType(models.TextChoices):
        CHANNEL = "channel", "Channel"
        THREAD = "thread", "Thread"

    target_type = models.CharField(max_length=20, choices=TargetType.choices)
    target_id = models.CharField(max_length=255)
    summary_text = models.TextField()
    generated_for = models.DateField(null=True, blank=True)
    model_used = models.CharField(max_length=100, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["target_type", "target_id"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.target_type}:{self.target_id}@{self.created_at:%Y-%m-%d %H:%M}"
