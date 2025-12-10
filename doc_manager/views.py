"""Views for document management API."""
from __future__ import annotations

import os
import re
import uuid
import threading

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth import authenticate
from django.core.files.storage import FileSystemStorage
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser

from .models import Document, DocumentChunk
from .serializers import (
    DocumentSerializer,
    DocumentDetailSerializer,
    DocumentUploadSerializer,
)
from slackbot.services.document_indexer import index_slack_files_and_summarize


FILE_STORAGE_ROOT = str(settings.FILE_STORAGE_DIR)
file_storage = FileSystemStorage(location=FILE_STORAGE_ROOT)


def _resolve_file_path(path: str | None) -> str | None:
    """Return an absolute path within the configured storage directory."""
    if not path:
        return None
    if os.path.isabs(path) and os.path.exists(path):
        return path
    normalized = path.lstrip("/")
    candidate = os.path.join(FILE_STORAGE_ROOT, normalized)
    if os.path.exists(candidate):
        return candidate
    return path if os.path.isabs(path) else candidate


def _build_storage_filename(original_name: str | None) -> str:
    """Return sanitized filename, appending random suffix if conflict occurs."""
    base_name = os.path.basename(original_name or "").strip() or "uploaded_file"
    sanitized = re.sub(r"[^\w.\-]+", "_", base_name)
    sanitized = sanitized.strip("._") or "uploaded_file"
    base, ext = os.path.splitext(sanitized)
    candidate = sanitized
    while file_storage.exists(candidate):
        suffix = uuid.uuid4().hex[:6]
        candidate = f"{base}_{suffix}{ext}"
    return candidate


def _process_document_background(document_id: int) -> None:
    """Process document in background thread."""
    try:
        document = Document.objects.get(id=document_id)
        file_path = _resolve_file_path(document.file_path)
        if not file_path or not os.path.exists(file_path):
            document.status = Document.ProcessingStatus.FAILED
            document.error_message = "原始文件不存在或无法读取"
            document.save(update_fields=["status", "error_message", "updated_at"])
            DocumentChunk.objects.filter(document=document).delete()
            return

        files = [{"name": document.original_name, "path": file_path}]
        result = index_slack_files_and_summarize(
            files,
            channel="web_upload",
            thread_ts=str(document_id),
        )

        summary_text = None
        chunk_payloads: list[dict[str, Any]] = []
        if isinstance(result, dict):
            summary_text = result.get("summary")
            chunk_payloads = result.get("chunks") or []
        else:
            summary_text = result
        
        summary_text = (summary_text or "").strip() or "文档处理完成"

        chunk_models: list[DocumentChunk] = []
        for idx, chunk in enumerate(chunk_payloads, start=1):
            text = str(chunk.get("text") or "").strip()
            if not text:
                continue
            chunk_models.append(
                DocumentChunk(
                    document=document,
                    chunk_index=int(chunk.get("index") or idx),
                    text=text,
                    metadata=chunk.get("metadata") or {},
                )
            )

        with transaction.atomic():
            document.status = Document.ProcessingStatus.COMPLETED
            document.summary = summary_text
            document.save(update_fields=["status", "summary", "updated_at"])
            DocumentChunk.objects.filter(document=document).delete()
            if chunk_models:
                chunk_models.sort(key=lambda chunk: chunk.chunk_index)
                DocumentChunk.objects.bulk_create(chunk_models)
        
    except Exception as exc:
        # Update document with error
        document = Document.objects.get(id=document_id)
        document.status = Document.ProcessingStatus.FAILED
        document.error_message = str(exc)
        document.save(update_fields=["status", "error_message", "updated_at"])
        DocumentChunk.objects.filter(document=document).delete()


class DocumentListView(APIView):
    """List and create documents."""
    
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        """Get list of documents with optional filtering."""
        status_filter = request.query_params.get("status", "all")
        search = request.query_params.get("search", "")
        
        queryset = Document.objects.all()
        
        if status_filter != "all":
            queryset = queryset.filter(status=status_filter)
        
        if search:
            queryset = queryset.filter(
                Q(original_name__icontains=search) | Q(name__icontains=search)
            )
        
        try:
            page = max(int(request.query_params.get("page", 1)), 1)
        except (TypeError, ValueError):
            page = 1

        try:
            page_size = int(request.query_params.get("page_size", 10))
        except (TypeError, ValueError):
            page_size = 10

        page_size = min(max(page_size, 1), 50)

        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        serializer = DocumentSerializer(page_obj.object_list, many=True)
        return Response(
            {
                "results": serializer.data,
                "count": paginator.count,
                "total_pages": paginator.num_pages or 1,
                "page": page_obj.number,
                "page_size": page_obj.paginator.per_page,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous(),
            }
        )
    
    def post(self, request, *args, **kwargs):
        """Upload a new document."""
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        uploaded_file = serializer.validated_data["file"]
        
        # Generate human-friendly filename with conflict handling
        stored_filename = _build_storage_filename(uploaded_file.name)
        
        # Save file
        stored_path = file_storage.save(stored_filename, uploaded_file)
        absolute_path = file_storage.path(stored_path)
        
        # Create document record
        document = Document.objects.create(
            name=stored_filename,
            original_name=uploaded_file.name,
            file_path=absolute_path,
            file_size=uploaded_file.size,
            content_type=uploaded_file.content_type,
            status=Document.ProcessingStatus.PENDING,
            processing_started_at=timezone.now(),
        )
        
        # Start background processing
        thread = threading.Thread(
            target=_process_document_background,
            args=(document.id,),
            daemon=True,
        )
        thread.start()
        
        serializer = DocumentSerializer(document)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class DocumentDetailView(APIView):
    """Retrieve, update, or delete a document."""
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk, *args, **kwargs):
        """Get document details."""
        try:
            document = Document.objects.prefetch_related("chunks").get(pk=pk)
            serializer = DocumentDetailSerializer(document)
            return Response(serializer.data)
        except Document.DoesNotExist:
            return Response({"error": "文档不存在"}, status=status.HTTP_404_NOT_FOUND)
    
    def delete(self, request, pk, *args, **kwargs):
        """Delete a document."""
        try:
            document = Document.objects.get(pk=pk)
            
            # Delete file from storage
            file_path = _resolve_file_path(document.file_path)
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            
            # Delete database record
            document.delete()
            
            return Response({"message": "文档已删除"}, status=status.HTTP_204_NO_CONTENT)
        except Document.DoesNotExist:
            return Response({"error": "文档不存在"}, status=status.HTTP_404_NOT_FOUND)


class DocumentReprocessView(APIView):
    """Trigger reprocessing of a failed document."""
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk, *args, **kwargs):
        try:
            document = Document.objects.get(pk=pk)
        except Document.DoesNotExist:
            return Response({"error": "文档不存在"}, status=status.HTTP_404_NOT_FOUND)
        
        now = timezone.now()
        can_reprocess = False

        if document.status == Document.ProcessingStatus.FAILED:
            can_reprocess = True
        elif document.status == Document.ProcessingStatus.PENDING:
            start_time = document.processing_started_at or document.created_at or now
            if now - start_time >= timedelta(minutes=30):
                can_reprocess = True
            else:
                return Response(
                    {"error": "处理中未超过30分钟，暂不可重新处理"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            return Response(
                {"error": "仅支持重新处理失败或卡住的文档"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        document.status = Document.ProcessingStatus.PENDING
        document.summary = ""
        document.error_message = ""
        document.processing_started_at = timezone.now()
        document.save(update_fields=["status", "summary", "error_message", "processing_started_at", "updated_at"])
        DocumentChunk.objects.filter(document=document).delete()
        
        thread = threading.Thread(
            target=_process_document_background,
            args=(document.id,),
            daemon=True,
        )
        thread.start()
        
        serializer = DocumentDetailSerializer(document)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)


class AuthLoginView(APIView):
    """Issue auth tokens for the management console."""

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        username = (request.data.get("username") or "").strip()
        password = (request.data.get("password") or "").strip()

        if not username or not password:
            return Response({"error": "请输入用户名和密码"}, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response({"error": "用户名或密码错误"}, status=status.HTTP_400_BAD_REQUEST)

        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "token": token.key,
                "user": {
                    "id": user.id,
                    "username": user.get_username(),
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                },
            }
        )


class AuthLogoutView(APIView):
    """Revoke auth tokens for the management console."""

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        auth_token = getattr(request, "auth", None)
        if auth_token is not None:
            try:
                auth_token.delete()
            except Exception:
                pass
        else:
            Token.objects.filter(user=request.user).delete()

        return Response({"success": True})
