"""Slack Web API helper functions."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Iterable, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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
        self.client.chat_postMessage(**payload)

    def download_shared_files(self, messages: Iterable[dict], download_dir: str | Path | None = None) -> list[Path]:
        """Download files that were shared in the provided messages.

        Slack includes shared file metadata alongside message payloads. Whenever a message
        contains a ``files`` array with ``url_private_download``/``url_private`` fields we
        fetch the file contents and persist them locally so that follow-up processing can
        read them (e.g. parsing uploaded documents after a mention).
        """

        downloads: list[Path] = []
        target_dir = Path(download_dir or settings.SLACK_FILE_DOWNLOAD_DIR)
        target_dir.mkdir(parents=True, exist_ok=True)

        for message in messages:
            for file_info in message.get("files", []) or []:
                file_url = file_info.get("url_private_download") or file_info.get("url_private")
                filename = file_info.get("name") or file_info.get("id")
                if not file_url or not filename:
                    continue

                destination = target_dir / filename
                try:
                    self._download_file(file_url, destination)
                except (HTTPError, URLError):  # pragma: no cover - network specific failures
                    continue
                downloads.append(destination)

        return downloads

    def _download_file(self, url: str, destination: Path) -> None:
        request = Request(url, headers={"Authorization": f"Bearer {self.token}"})
        with urlopen(request) as response:  # nosec: B310 - trusted Slack domain with auth
            destination.write_bytes(response.read())


def format_messages_for_prompt(messages: Iterable[dict]) -> str:
    """Convert Slack messages to a human readable transcript."""
    formatted = []
    for entry in messages:
        user = entry.get("user") or entry.get("username", "Unknown")
        ts = entry.get("ts")
        text = entry.get("text", "")
        formatted.append(f"[{ts}] {user}: {text}")
    return "\n".join(formatted)
