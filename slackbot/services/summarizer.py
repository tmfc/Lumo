"""Utilities that talk to a LiteLLM-compatible proxy for summarization.

The proxy is treated as an OpenAI-compatible endpoint so that custom model
identifiers configured on the proxy are passed through unchanged.
"""
from __future__ import annotations

from typing import Iterable, Sequence

from django.conf import settings
import os

try:  # pragma: no cover
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore


class SlackAssistant:
    """Generic LLM-backed assistant for Slack conversations."""

    def __init__(self, model: str | None = None):
        self.model = model or settings.SLACK_DEFAULT_SUMMARY_MODEL
        if not self.model:
            raise RuntimeError("Set LITELLM_MODEL or SLACK_DEFAULT_SUMMARY_MODEL in the environment.")
        if OpenAI is None:
            raise RuntimeError("openai is not installed. Install it to summarize conversations.")

    def summarize(self, transcript: str, instruction: str | None = None) -> str:
        # Generic assistant-style system prompt. The concrete task (summarize,
        # answer a question, brainstorm, etc.) is expressed in the user's
        # message / transcript. The model should detect the user's language and
        # respond in that same language.
        system_prompt = instruction or (
            "You are a helpful assistant for Slack conversations. "
            "Use the provided Slack context and the user's instructions to complete the task. "
            "First, infer what the user wants (e.g., summary, explanation, plan, code, answer). "
            "Then respond clearly and concisely in the same primary language as the user's request."
        )
        # Minimal debug output: show prompt and final reply for troubleshooting.
        print("[Summarizer] Model:", self.model)
        print("[Summarizer] System prompt:", system_prompt)
        print("[Summarizer] User transcript (truncated):", transcript[:500])

        base_url = os.getenv("LITELLM_BASE_URL")
        api_key = os.getenv("LITELLM_API_KEY")
        if not base_url or not api_key:
            raise RuntimeError("LITELLM_BASE_URL and LITELLM_API_KEY must be set to use the proxy.")

        client = OpenAI(base_url=base_url.rstrip("/"), api_key=api_key)

        # Use a small, deterministic completion with a timeout so health checks
        # cannot hang indefinitely if the upstream provider has issues.
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": transcript},
            ],
            temperature=0.2,
            max_tokens=4096,
            timeout=15,
        )

        # Be defensive about the response shape: different OpenAI-compatible
        # backends may return message content as a string, a list of chunks, or
        # a plain dict.
        choice = response.choices[0]
        message = getattr(choice, "message", choice)
        content = getattr(message, "content", None)
        if content is None and isinstance(message, dict):
            content = message.get("content")

        # When content is a list (e.g. content blocks), concatenate text parts.
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    # Common OpenAI-compatible shape: {"type": "text", "text": "..."}
                    text = part.get("text") or part.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            content = "".join(parts)

        if not isinstance(content, str):
            # Fall back to a safe string representation so the Slack flow does
            # not crash completely, even if formatting is suboptimal.
            text = str(content)
        else:
            text = content.strip()

        print("[Summarizer] LLM reply (truncated):", text[:500])
        return text


def build_summary_prompt(messages: Iterable[dict], scope_description: str) -> str:
    """Create a readable prompt that includes guidance on what to summarize."""
    lines = [
        f"Summarize the following Slack {scope_description}.",
        "Return a concise bullet list of the key points, decisions, and follow-ups.",
        "\nConversation:\n",
    ]
    for entry in messages:
        user = entry.get("user") or entry.get("username", "Unknown")
        text = entry.get("text", "")
        timestamp = entry.get("ts", "")
        lines.append(f"- ({timestamp}) {user}: {text}")
    return "\n".join(lines)


def build_question_prompt(
    *,
    question: str,
    context_text: str | None = None,
    memories: Sequence[str] | None = None,
) -> str:
    """Create a prompt that instructs the model to answer a question."""

    sanitized_question = question.strip()
    lines = [
        "You are answering a Slack question about the Lumo Slack bot project.",
        "Respond using the provided Slack context and project memory snippets.",
        f"Question: {sanitized_question}",
    ]

    if context_text:
        lines.append("\nRecent Slack context:\n")
        lines.append(context_text.strip())

    if memories:
        lines.append("\nProject memory snippets:\n")
        for idx, memory in enumerate(memories, start=1):
            lines.append(f"{idx}. {memory.strip()}")

    lines.append("\nAnswer:")
    return "\n".join(lines)
