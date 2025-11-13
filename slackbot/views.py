"""Django REST Framework views for Slack integration."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ConversationSummary
from .serializers import ChannelSummarySerializer, SlackEventSerializer, ThreadSummarySerializer
from .services.memory import SummaryMemory
from .services.slack_client import SlackClient, format_messages_for_prompt
from .services.summarizer import Summarizer, build_question_prompt, build_summary_prompt

logger = logging.getLogger(__name__)


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

    try:
        memory = SummaryMemory(user_id=mem0_user_id)
    except RuntimeError as exc:  # pragma: no cover - misconfiguration warning
        logger.warning("mem0 memory is configured incorrectly: %s", exc)
        return

    memory.remember_summary(
        summary_text=summary_text,
        target_type=target_type,
        target_id=target_id,
        generated_for=generated_for,
        model_used=model_used,
        metadata=metadata,
    )


class SlackEventView(APIView):
    """Handle inbound Slack Events API payloads."""

    def post(self, request, *args, **kwargs):  # pragma: no cover - requires Slack payloads
        serializer = SlackEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        if payload["type"] == "url_verification":
            return Response({"challenge": payload.get("challenge")})

        event = payload.get("event", {})
        event_type = event.get("type")
        if event_type == "app_mention":
            response_text = self._handle_app_mention(event)
            return Response({"ok": True, "message": response_text})

        return Response({"ok": True})

    def _handle_app_mention(self, event: Dict[str, Any]) -> str:
        text = event.get("text", "")
        if "summary" in text.lower():
            return self._handle_summary_request(event)
        return self._answer_question(event)

    def _handle_summary_request(self, event: Dict[str, Any]) -> str:
        channel = event.get("channel")
        thread_ts = event.get("thread_ts")

        slack_client = SlackClient()
        summarizer = Summarizer()

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

        summary = summarizer.summarize(prompt)
        slack_client.post_message(channel, summary, thread_ts=thread_ts)
        generated_for = timezone.now().date()
        record = ConversationSummary.objects.create(
            target_type="thread" if thread_ts else "channel",
            target_id=thread_ts or channel,
            summary_text=summary,
            generated_for=generated_for,
            model_used=summarizer.model,
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

    def _answer_question(self, event: Dict[str, Any]) -> str:
        channel = event.get("channel")
        thread_ts = event.get("thread_ts")
        question_text = event.get("text", "")

        slack_client = SlackClient()
        summarizer = Summarizer()

        now = timezone.now()
        context_start = now - dt.timedelta(hours=24)
        messages = slack_client.fetch_channel_messages(
            channel,
            start=context_start,
            end=now,
            limit=settings.SLACK_SUMMARY_MAX_MESSAGES,
        )
        context_text = format_messages_for_prompt(messages)

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
            "Answer the user's question using the provided Slack context and project memories. "
            "If the answer cannot be determined, say you are unsure instead of guessing."
        )
        answer = summarizer.summarize(prompt, instruction=instruction)
        slack_client.post_message(channel, answer, thread_ts=thread_ts)
        return answer


class ChannelSummaryView(APIView):
    """Summarize a Slack channel for a specific day or date range."""

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
        summary = summarizer.summarize(transcript)

        generated_for = target_date or start_dt.date()
        record = ConversationSummary.objects.create(
            target_type="channel",
            target_id=channel_id,
            summary_text=summary,
            generated_for=generated_for,
            model_used=summarizer.model,
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
        summary = summarizer.summarize(transcript)

        generated_for = timezone.now().date()
        record = ConversationSummary.objects.create(
            target_type="thread",
            target_id=thread_ts,
            summary_text=summary,
            generated_for=generated_for,
            model_used=summarizer.model,
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
