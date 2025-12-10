"""Django REST Framework views for Slack integration."""
from __future__ import annotations

import datetime as dt
import logging
import os
import threading
from typing import Any, Dict

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
import requests
from llama_index.core import Document

from .models import ConversationSummary, ProcessedSlackEvent
from .serializers import ChannelSummarySerializer, SlackEventSerializer, ThreadSummarySerializer
from .services.slack_client import SlackClient, format_messages_for_prompt
from .services.summarizer import SlackAssistant, build_question_prompt, build_summary_prompt
from .services.document_indexer import index_slack_files_and_summarize, query_slack_file_context

logger = logging.getLogger(__name__)


SLACK_DOWNLOAD_DIR = str(
    getattr(
        settings,
        "FILE_STORAGE_DIR",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "downloads"),
    )
)


def _log_and_download_slack_files(event: Dict[str, Any]) -> Dict[str, Any] | bool:
    """Log Slack file objects in the event and download them to a fixed folder.

    This helps verify the exact structure of Slack file payloads and stores
    uploaded files locally under SLACK_DOWNLOAD_DIR. It also uses LlamaIndex's
    Document as a simple way to wrap event context.
    """

    files = event.get("files") or []
    if not files:
        return False

    # Log raw file objects for inspection
    logger.info("[SlackEventView] Received Slack files: %s", files)

    # Use LlamaIndex Document to wrap basic context (for later retrieval/analysis if desired)
    try:
        _ = Document(text=str(event), metadata={"source": "slack_event", "has_files": True})
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[SlackEventView] Failed to create LlamaIndex Document for event: %s", exc)

    # Ensure download directory exists
    os.makedirs(SLACK_DOWNLOAD_DIR, exist_ok=True)

    token = settings.SLACK_BOT_TOKEN
    if not token:
        logger.warning("[SlackEventView] SLACK_BOT_TOKEN is not set; cannot download Slack files.")
        return

    headers = {"Authorization": f"Bearer {token}"}

    any_saved = False
    downloaded_files: list[dict[str, Any]] = []

    for file_obj in files:
        url = (
            file_obj.get("url_private_download")
            or file_obj.get("url_private")
            or file_obj.get("permalink_public")
        )
        name = file_obj.get("name") or file_obj.get("id") or "unnamed_file"

        if not url:
            logger.info("[SlackEventView] File object has no downloadable URL: %s", file_obj)
            continue

        try:
            logger.info("[SlackEventView] Downloading Slack file: name=%s url=%s", name, url)
            resp = requests.get(url, headers=headers, stream=True, timeout=30)
            resp.raise_for_status()

            safe_name = "".join(c for c in name if c not in "\\/:*?\"<>|") or "downloaded_file"
            base, ext = os.path.splitext(safe_name)
            candidate = safe_name
            counter = 1
            while os.path.exists(os.path.join(SLACK_DOWNLOAD_DIR, candidate)):
                candidate = f"{base}_{counter}{ext}"
                counter += 1
            dest_path = os.path.join(SLACK_DOWNLOAD_DIR, candidate)

            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            logger.info("[SlackEventView] Saved Slack file to: %s", dest_path)
            any_saved = True
            downloaded_files.append({"name": name, "path": dest_path})
        except Exception as exc:  # pragma: no cover - runtime only
            logger.warning(
                "[SlackEventView] Failed to download Slack file name=%s url=%s error=%s",
                name,
                url,
                exc,
            )

    if not any_saved:
        return False

    return {"downloaded": True, "files": downloaded_files}


def _remember_summary(
    *,
    summary_text: str,
    target_type: str,
    target_id: str,
    generated_for: dt.date | None,
    model_used: str,
    metadata: Dict[str, Any] | None = None,
    mem0_user_id: str | None = None,
):
    """Send the generated summary to mem0.ai if it is configured."""
    # mem0 集成功能已关闭，此处保留空实现以保持向后兼容。
    return


def _run_file_indexing_background(channel: str, ts: str, download_result: Dict[str, Any]) -> None:
    """Run LlamaIndex indexing and summarization in a background thread.

    This keeps the HTTP request fast while still sending a follow-up summary
    message once indexing is complete.
    """

    logger.info("[_run_file_indexing_background] start: channel=%s ts=%s download_result=%s", channel, ts, download_result)
    print("[_run_file_indexing_background] start", channel, ts, download_result)

    if not (isinstance(download_result, dict) and download_result.get("downloaded")):
        logger.info("[_run_file_indexing_background] download_result not valid, skip indexing")
        print("[_run_file_indexing_background] invalid download_result, skip")
        return

    files = download_result.get("files") or []
    try:
        result = index_slack_files_and_summarize(
            files,
            channel=channel,
            thread_ts=ts,
        )
        if isinstance(result, dict):
            summary = result.get("summary")
        else:
            summary = result
        logger.info("[_run_file_indexing_background] indexing finished, summary_present=%s", bool(summary))
        print("[_run_file_indexing_background] indexing finished, summary_present=", bool(summary))
    except Exception as exc:  # pragma: no cover - 运行时故障不影响主流程
        logger.exception("[_run_file_indexing_background] indexing failed: %s", exc)
        print("[_run_file_indexing_background] indexing failed", exc)
        summary = None

    if not summary:
        logger.info("[_run_file_indexing_background] no summary generated, nothing to send")
        print("[_run_file_indexing_background] no summary generated")
        return

    try:
        SlackClient().post_message(channel, summary, thread_ts=ts)
        logger.info("[_run_file_indexing_background] summary message sent to Slack")
        print("[_run_file_indexing_background] summary message sent to Slack")
    except Exception as exc:  # pragma: no cover - 运行时故障不影响主流程
        logger.exception("[_run_file_indexing_background] failed to send summary message: %s", exc)
        print("[_run_file_indexing_background] failed to send summary message", exc)
        return


class SlackEventView(APIView):
    """Handle inbound Slack Events API payloads."""

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):  # pragma: no cover - requires Slack payloads
        print("[SlackEventView] Received Slack payload:", request.data)
        serializer = SlackEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        # Log and download any Slack file objects present in the event
        event_for_files = payload.get("event") or {}
        download_result = _log_and_download_slack_files(event_for_files)

        event_id = payload.get("event_id")
        if event_id:
            obj, created = ProcessedSlackEvent.objects.get_or_create(event_id=event_id)
            if not created:
                print("[SlackEventView] Duplicate event_id (DB), ignoring:", event_id)
                return Response({"ok": True, "duplicate": True})

        if payload["type"] == "url_verification":
            return Response({"challenge": payload.get("challenge")})

        event = payload.get("event", {})
        event_type = event.get("type")
        print("[SlackEventView] Handling Slack event type:", event_type)

        # 如果成功下载了 Slack 附件，并且这是一次 app_mention，则直接回复固定文案，不再调用 LLM
        if download_result and event_type == "app_mention":
            channel = event.get("channel")
            ts = event.get("ts")
            if channel and ts:
                try:
                    SlackClient().post_message(channel, "已成功下载你发的文件，我正在阅读中，稍后再帮你分析。", thread_ts=ts)
                except Exception:  # pragma: no cover - 运行时故障不影响主流程
                    pass

                # 使用 LlamaIndex 对刚下载的文件进行索引和简要分析，并把结果发回同一线程
                # 为了不阻塞当前 HTTP 请求，这里使用后台线程执行索引与摘要逻辑。
                thread = threading.Thread(
                    target=_run_file_indexing_background,
                    args=(channel, ts, download_result),
                    daemon=True,
                )
                thread.start()

            return Response({"ok": True, "downloaded_files": True})
        if event_type == "app_mention":
            response_text = self._handle_app_mention(event)
            return Response({"ok": True, "message": response_text})

        return Response({"ok": True})

    def _handle_app_mention(self, event: Dict[str, Any]) -> str:
        channel = event.get("channel")
        ts = event.get("ts")
        text = event.get("text", "")
        message = event.get("message") or {}
        lower_text = text.lower()

        # 先用一个 "ok_hand" 表情回应，表示请求已接受
        if channel and ts:
            try:
                SlackClient().add_reaction(channel, ts, "ok_hand")
            except Exception:
                # 表情失败不影响主流程
                pass

        # 简单关键字路由：包含 summary / summarize 或中文“总结”时走摘要逻辑
        if "summary" in lower_text or "summarize" in lower_text or "总结" in text:
            return self._handle_summary_request(event)

        # 当用户对某条消息使用 mention 触发机器人时，优先针对该消息内容调用问答流程
        if isinstance(message, dict) and message.get("text"):
            return self._answer_question(event, question_override=message.get("text", ""))

        # 其他情况默认走问答流程
        return self._answer_question(event)

    def _handle_summary_request(self, event: Dict[str, Any]) -> str:
        channel = event.get("channel")
        thread_ts = event.get("thread_ts")

        slack_client = SlackClient()
        assistant = SlackAssistant()

        if thread_ts:
            messages = slack_client.fetch_thread_messages(channel, thread_ts, settings.SLACK_SUMMARY_MAX_MESSAGES)
            prompt = build_summary_prompt(messages, "thread")
        else:
            now = timezone.now()
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            messages = slack_client.fetch_channel_messages(
                channel,
                start=start_of_day,
                end=now,
                limit=settings.SLACK_SUMMARY_MAX_MESSAGES,
            )
            prompt = build_summary_prompt(messages, "channel conversations for today")

        summary = assistant.summarize(prompt)
        slack_client.post_message(channel, summary, thread_ts=thread_ts)
        generated_for = timezone.now().date()
        record = ConversationSummary.objects.create(
            target_type="thread" if thread_ts else "channel",
            target_id=thread_ts or channel,
            summary_text=summary,
            generated_for=generated_for,
            model_used=assistant.model,
        )
        _remember_summary(
            summary_text=record.summary_text,
            target_type=record.target_type,
            target_id=record.target_id,
            generated_for=record.generated_for,
            model_used=record.model_used,
            metadata={
                "channel_id": channel,
                "thread_ts": thread_ts,
                "source": "app_mention",
            },
            mem0_user_id=event.get("team") or event.get("team_id"),
        )
        return summary

    def _answer_question(self, event: Dict[str, Any], question_override: str | None = None) -> str:
        channel = event.get("channel")
        thread_ts = event.get("thread_ts")
        question_text = question_override or event.get("text", "")

        slack_client = SlackClient()
        assistant = SlackAssistant()

        now = timezone.now()
        context_start = now - dt.timedelta(hours=24)
        messages = slack_client.fetch_channel_messages(
            channel,
            start=context_start,
            end=now,
            limit=settings.SLACK_SUMMARY_MAX_MESSAGES,
        )
        context_text = format_messages_for_prompt(messages)

        # 从 LlamaIndex 中检索与当前问题相关的文档片段，作为额外上下文
        try:
            file_context = query_slack_file_context(
                channel=channel,
                thread_ts=thread_ts,
                question=question_text,
            )
        except Exception:  # pragma: no cover - 运行时故障不影响主流程
            file_context = ""

        if file_context:
            context_text = f"[File context from uploaded documents]\n{file_context}\n\n[Slack messages]\n{context_text}"

        target_type = "thread" if thread_ts else "channel"
        target_id = thread_ts or channel
        recent_memories = list(
            ConversationSummary.objects.filter(target_type=target_type, target_id=target_id)
            .order_by("-created_at")
            .values_list("summary_text", flat=True)[:5]
        )

        prompt = build_question_prompt(
            question=question_text,
            context_text=context_text,
            memories=recent_memories,
        )
        instruction = (
            "You are a helpful assistant for the Lumo Slack bot project. "
            "When helpful, use the provided Slack context and project memories to ground your answer. "
            "If the context does not contain the needed information, answer from your own general knowledge instead. "
            "If even then the answer is unclear, say you are unsure instead of guessing."
        )
        answer = assistant.summarize(prompt, instruction=instruction)
        slack_client.post_message(channel, answer, thread_ts=thread_ts)
        return answer


class ChannelSummaryView(APIView):
    """Summarize a Slack channel for a specific day or date range."""

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = ChannelSummarySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        channel_id = serializer.validated_data["channel_id"]
        target_date = serializer.get_target_date()
        start_date = serializer.validated_data.get("start_date")
        end_date = serializer.validated_data.get("end_date")
        max_messages = serializer.validated_data.get("max_messages", settings.SLACK_SUMMARY_MAX_MESSAGES)

        if target_date:
            start_dt = dt.datetime.combine(target_date, dt.time.min, tzinfo=timezone.utc)
            end_dt = dt.datetime.combine(target_date, dt.time.max, tzinfo=timezone.utc)
            scope_text = f"channel conversations for {target_date.isoformat()}"
        else:
            start_dt = dt.datetime.combine(start_date or timezone.now().date(), dt.time.min, tzinfo=timezone.utc)
            end_dt = dt.datetime.combine(end_date or timezone.now().date(), dt.time.max, tzinfo=timezone.utc)
            scope_text = f"channel conversations from {start_dt.date()} to {end_dt.date()}"

        slack_client = SlackClient()
        summarizer = Summarizer()

        messages = slack_client.fetch_channel_messages(channel_id, start=start_dt, end=end_dt, limit=max_messages)
        transcript = build_summary_prompt(messages, scope_text)
        summary = assistant.summarize(transcript)

        generated_for = target_date or start_dt.date()
        record = ConversationSummary.objects.create(
            target_type="channel",
            target_id=channel_id,
            summary_text=summary,
            generated_for=generated_for,
            model_used=assistant.model,
        )
        _remember_summary(
            summary_text=record.summary_text,
            target_type=record.target_type,
            target_id=record.target_id,
            generated_for=record.generated_for,
            model_used=record.model_used,
            metadata={
                "channel_id": channel_id,
                "source": "channel-summary-endpoint",
                "scope": scope_text,
            },
            mem0_user_id=serializer.validated_data.get("mem0_user_id"),
        )
        return Response({"summary": record.summary_text, "model": record.model_used})


class ThreadSummaryView(APIView):
    """Summarize a specific Slack thread."""

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = ThreadSummarySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        channel_id = serializer.validated_data["channel_id"]
        thread_ts = serializer.validated_data["thread_ts"]
        max_messages = serializer.validated_data.get("max_messages", settings.SLACK_SUMMARY_MAX_MESSAGES)

        slack_client = SlackClient()
        summarizer = Summarizer()

        messages = slack_client.fetch_thread_messages(channel_id, thread_ts, limit=max_messages)
        transcript = build_summary_prompt(messages, "thread")
        summary = assistant.summarize(transcript)

        generated_for = timezone.now().date()
        record = ConversationSummary.objects.create(
            target_type="thread",
            target_id=thread_ts,
            summary_text=summary,
            generated_for=generated_for,
            model_used=assistant.model,
        )
        _remember_summary(
            summary_text=record.summary_text,
            target_type=record.target_type,
            target_id=record.target_id,
            generated_for=record.generated_for,
            model_used=record.model_used,
            metadata={
                "channel_id": channel_id,
                "thread_ts": thread_ts,
                "source": "thread-summary-endpoint",
            },
            mem0_user_id=serializer.validated_data.get("mem0_user_id"),
        )
        return Response({"summary": record.summary_text, "model": record.model_used})


class HealthView(APIView):
    """Simple health endpoint for uptime checks."""

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request, *args, **kwargs):
        return Response({"status": "ok"})


class DiagnosticsView(APIView):
    """Composite health check for LiteLLM, mem0, and Qdrant."""

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request, *args, **kwargs):  # pragma: no cover - runtime diagnostics
        data: Dict[str, Any] = {
            "litellm": {"ok": False},
        }

        # LiteLLM / LLM backend check
        try:
            assistant = SlackAssistant()
            # Use a tiny prompt to minimize latency and cost
            summary = assistant.summarize("ping", instruction="Reply with a single word: pong")
            data["litellm"] = {"ok": True, "sample_response": summary}
        except Exception as exc:  # pragma: no cover - diagnostics only
            data["litellm"] = {"ok": False, "error": str(exc)}

        return Response(data, status=status.HTTP_200_OK)
