"""Serializers for document management API."""
from __future__ import annotations

import math
import re
from datetime import timedelta
from typing import Any, List

from django.utils import timezone
from rest_framework import serializers
from .models import Document, DocumentChunk


def _format_file_size(size: int | None) -> str:
    """Return a human-readable file size string."""
    if size is None:
        return "--"
    if size == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = min(int(math.log(size, 1024)), len(units) - 1) if size > 0 else 0
    value = size / (1024**idx)
    return f"{value:.2f} {units[idx]}"


def _split_text_into_chunks(text: str, chunk_size: int = 280, max_chunks: int = 12) -> List[str]:
    """Split free-form text into soft chunks for display."""
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    
    # Split by punctuation and newlines, then regroup to target length
    parts = [p.strip() for p in re.split(r"(?<=[。！？.!?])\s+|\n+", cleaned) if p.strip()]
    if not parts:
        parts = [cleaned]
    
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    
    for part in parts:
        part_len = len(part)
        if current and current_len + part_len > chunk_size:
            chunks.append(" ".join(current).strip())
            current = [part]
            current_len = part_len
        else:
            current.append(part)
            current_len += part_len
    
    if current:
        chunks.append(" ".join(current).strip())
    
    return chunks[:max_chunks]


def _format_duration(seconds: float | None) -> str:
    """Format processing duration in a friendly manner."""
    if seconds is None:
        return "--"
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"{seconds:.1f}秒"
    
    minutes = int(seconds // 60)
    remaining = seconds % 60
    if minutes >= 60:
        hours = minutes // 60
        minutes = minutes % 60
        return f"{hours}小时{minutes}分"
    return f"{minutes}分{remaining:.0f}秒" if remaining else f"{minutes}分钟"


class DocumentSerializer(serializers.ModelSerializer):
    """Serializer for Document model."""
    
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    
    class Meta:
        model = Document
        fields = [
            "id",
            "name",
            "original_name",
            "file_size",
            "content_type",
            "status",
            "status_display",
            "summary",
            "error_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "name",
            "file_size",
            "content_type",
            "status",
            "summary",
            "error_message",
            "created_at",
            "updated_at",
        ]


class DocumentDetailSerializer(DocumentSerializer):
    """Detailed serializer that augments base document info."""
    
    preview_text = serializers.SerializerMethodField()
    chunks = serializers.SerializerMethodField()
    chunk_count = serializers.SerializerMethodField()
    processing_duration_seconds = serializers.SerializerMethodField()
    processing_duration_display = serializers.SerializerMethodField()
    file_size_display = serializers.SerializerMethodField()
    uploaded_at_display = serializers.SerializerMethodField()
    
    class Meta(DocumentSerializer.Meta):
        fields = DocumentSerializer.Meta.fields + [
            "preview_text",
            "chunks",
            "chunk_count",
            "processing_duration_seconds",
            "processing_duration_display",
            "file_size_display",
            "uploaded_at_display",
        ]
    
    def _get_document_chunks(self, obj: Document) -> List[DocumentChunk]:
        cache_key = "_prefetched_document_chunks"
        cached = getattr(obj, cache_key, None)
        if cached is None:
            cached = list(obj.chunks.all().order_by("chunk_index"))
            setattr(obj, cache_key, cached)
        return cached
    
    def _get_summary_chunks(self, obj: Document) -> List[str]:
        cache_key = "_computed_summary_chunks"
        cached = getattr(obj, cache_key, None)
        if cached is None:
            cached = _split_text_into_chunks((obj.summary or "").strip())
            setattr(obj, cache_key, cached)
        return cached
    
    def get_preview_text(self, obj: Document) -> str:
        summary = (obj.summary or "").strip()
        if summary:
            return summary
        if obj.status == Document.ProcessingStatus.PENDING:
            return "文档正在处理中，请稍后再试。"
        if obj.status == Document.ProcessingStatus.FAILED:
            return obj.error_message or "文档处理失败。"
        return "暂时没有可以展示的摘要。"
    
    def get_chunks(self, obj: Document) -> List[dict[str, Any]]:
        chunk_records = self._get_document_chunks(obj)
        if chunk_records:
            return [
                {
                    "index": chunk.chunk_index,
                    "text": chunk.text,
                    "metadata": chunk.metadata or {},
                }
                for chunk in chunk_records
            ]
        summary_chunks = self._get_summary_chunks(obj)
        return [{"index": idx + 1, "text": chunk} for idx, chunk in enumerate(summary_chunks)]
    
    def get_chunk_count(self, obj: Document) -> int:
        chunk_records = self._get_document_chunks(obj)
        if chunk_records:
            return len(chunk_records)
        return len(self._get_summary_chunks(obj))
    
    def get_processing_duration_seconds(self, obj: Document) -> float | None:
        start = obj.processing_started_at or obj.created_at
        if not start:
            return None
        if obj.status == Document.ProcessingStatus.PENDING:
            delta = timezone.now() - start
            return max(delta.total_seconds(), 0.0)
        if not obj.updated_at:
            return None
        delta: timedelta = obj.updated_at - start
        return max(delta.total_seconds(), 0.0)
    
    def get_processing_duration_display(self, obj: Document) -> str:
        seconds = self.get_processing_duration_seconds(obj)
        return _format_duration(seconds)
    
    def get_file_size_display(self, obj: Document) -> str:
        return _format_file_size(obj.file_size)
    
    def get_uploaded_at_display(self, obj: Document) -> str:
        if not obj.created_at:
            return "--"
        return obj.created_at.strftime("%Y-%m-%d %H:%M")


class DocumentUploadSerializer(serializers.Serializer):
    """Serializer for document upload."""
    file = serializers.FileField()
    
    def validate_file(self, value):
        """Validate uploaded file."""
        # Check file size (max 50MB)
        max_size = 50 * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError("文件大小不能超过50MB")
        
        # Check file type
        allowed_types = [
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/plain",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ]
        
        if value.content_type not in allowed_types:
            raise serializers.ValidationError(
                "不支持的文件类型。支持的类型：PDF, DOC, DOCX, TXT, XLS, XLSX"
            )
        
        return value
