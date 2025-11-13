"""Utilities that talk to LiteLLM for summarization."""
from __future__ import annotations

from typing import Iterable, Sequence

from django.conf import settings

try:  # pragma: no cover
    import litellm
except ImportError:  # pragma: no cover
    litellm = None  # type: ignore


class Summarizer:
    """Generate summaries using LiteLLM compatible models."""

    def __init__(self, model: str | None = None):
        self.model = model or settings.SLACK_DEFAULT_SUMMARY_MODEL
        if not self.model:
            raise RuntimeError("Set LITELLM_MODEL or SLACK_DEFAULT_SUMMARY_MODEL in the environment.")
        if litellm is None:
            raise RuntimeError("litellm is not installed. Install it to summarize conversations.")

    def summarize(self, transcript: str, instruction: str | None = None) -> str:
        system_prompt = instruction or (
            "You are an assistant that summarizes Slack conversations. "
            "Highlight decisions, blockers, and next steps."
        )
        response = litellm.completion(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": transcript},
            ],
            temperature=0.2,
        )
        return response.choices[0].message["content"].strip()


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
