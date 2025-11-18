"""Slack Web API helper functions."""
from __future__ import annotations

import datetime as dt
from typing import Iterable, List

from django.conf import settings

try:  # pragma: no cover - import guarded for environments without slack_sdk
    from slack_sdk import WebClient
except ImportError:  # pragma: no cover - fallback for docs/tests
    WebClient = None  # type: ignore


class SlackClient:
    """Thin wrapper around the Slack WebClient."""

    def __init__(self, token: str | None = None):
        self.token = token or settings.SLACK_BOT_TOKEN
        if not self.token:
            raise RuntimeError("Missing Slack bot token. Set SLACK_BOT_TOKEN in the environment.")
        if WebClient is None:
            raise RuntimeError("slack_sdk is not installed. Install it to use the Slack client.")
        self.client = WebClient(token=self.token)

    def fetch_channel_messages(
        self,
        channel_id: str,
        start: dt.datetime,
        end: dt.datetime,
        limit: int,
    ) -> List[dict]:
        """Return messages from a channel bounded by the provided dates."""
        response = self.client.conversations_history(
            channel=channel_id,
            oldest=start.timestamp(),
            latest=end.timestamp(),
            limit=limit,
            inclusive=True,
        )
        return response.get("messages", [])

    def fetch_thread_messages(self, channel_id: str, thread_ts: str, limit: int) -> List[dict]:
        """Return every message in a thread, regardless of date."""
        response = self.client.conversations_replies(channel=channel_id, ts=thread_ts, limit=limit)
        return response.get("messages", [])

    def post_message(self, channel_id: str, text: str, thread_ts: str | None = None) -> None:
        """Send a reply back to Slack."""
        payload = {"channel": channel_id, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        try:
            response = self.client.chat_postMessage(**payload)
            print("[SlackClient] chat_postMessage OK:", response.data)
        except Exception as exc:  # pragma: no cover - runtime diagnostics
            print("[SlackClient] Failed to post message:", exc)

    def add_reaction(self, channel_id: str, timestamp: str, name: str) -> None:
        """Add an emoji reaction to a Slack message."""
        try:
            response = self.client.reactions_add(channel=channel_id, timestamp=timestamp, name=name)
            print("[SlackClient] reactions_add OK:", response.data)
        except Exception as exc:  # pragma: no cover - runtime diagnostics
            print("[SlackClient] Failed to add reaction:", exc)


def format_messages_for_prompt(messages: Iterable[dict]) -> str:
    """Convert Slack messages to a human readable transcript."""
    formatted = []
    for entry in messages:
        user = entry.get("user") or entry.get("username", "Unknown")
        ts = entry.get("ts")
        text = entry.get("text", "")
        formatted.append(f"[{ts}] {user}: {text}")
    return "\n".join(formatted)
