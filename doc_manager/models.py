"""Database models for document management."""
from __future__ import annotations

import os
from django.db import models
from django.utils import timezone


class Document(models.Model):
    """Stores uploaded document information and processing status."""
    
    class ProcessingStatus(models.TextChoices):
        PENDING = "pending", "处理中"
        COMPLETED = "completed", "已完成"
        FAILED = "failed", "失败"
    
    name = models.CharField(max_length=255)
    original_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    file_size = models.BigIntegerField()
    content_type = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20, 
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING
    )
    summary = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processing_started_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]
    
    def __str__(self) -> str:
        return f"{self.name} ({self.get_status_display()})"


class DocumentChunk(models.Model):
    """Stores semantic chunk text for a processed document."""

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    chunk_index = models.PositiveIntegerField()
    text = models.TextField()
    metadata = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["chunk_index"]
        unique_together = ("document", "chunk_index")

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return f"{self.document_id}#{self.chunk_index}"
