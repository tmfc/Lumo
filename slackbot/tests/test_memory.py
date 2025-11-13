"""Tests for the mem0 integration helper."""
from __future__ import annotations

import datetime as dt
from unittest import mock

from django.test import SimpleTestCase, override_settings

from slackbot.services.memory import SummaryMemory


class SummaryMemoryTests(SimpleTestCase):
    """Ensure summaries can be persisted to mem0 when configured."""

    @override_settings(MEM0_API_KEY="")
    @mock.patch("slackbot.services.memory.Mem0Memory")
    def test_disabled_when_no_api_key(self, memory_cls):
        memory = SummaryMemory()
        self.assertFalse(memory.enabled)
        memory.remember_summary(
            summary_text="text",
            target_type="channel",
            target_id="C1",
        )
        memory_cls.assert_not_called()

    @override_settings(MEM0_API_KEY="secret", MEM0_DEFAULT_USER_ID="lumo")
    @mock.patch("slackbot.services.memory.Mem0Memory")
    def test_records_summary_metadata(self, memory_cls):
        client = memory_cls.return_value
        memory = SummaryMemory()
        memory.remember_summary(
            summary_text="A summary",
            target_type="channel",
            target_id="C123",
            generated_for=dt.date(2024, 5, 1),
            model_used="gpt-4",
            metadata={"scope": "channel"},
        )

        memory_cls.assert_called_once_with(api_key="secret")
        client.add.assert_called_once()
        _, kwargs = client.add.call_args
        self.assertEqual(kwargs["user_id"], "lumo")
        self.assertEqual(kwargs["metadata"]["target_id"], "C123")
        self.assertEqual(kwargs["metadata"]["scope"], "channel")
        self.assertEqual(kwargs["metadata"]["generated_for"], "2024-05-01")

    @override_settings(MEM0_API_KEY="secret", MEM0_DEFAULT_USER_ID="lumo")
    @mock.patch("slackbot.services.memory.Mem0Memory")
    def test_user_id_can_be_overridden(self, memory_cls):
        client = memory_cls.return_value
        memory = SummaryMemory(user_id="team-123")
        memory.remember_summary(
            summary_text="summary",
            target_type="channel",
            target_id="C555",
        )

        _, kwargs = client.add.call_args
        self.assertEqual(kwargs["user_id"], "team-123")

    @override_settings(
        MEM0_API_KEY="secret",
        MEM0_DEFAULT_USER_ID="lumo",
        MEM0_BASE_URL="https://mem0.internal",
    )
    @mock.patch("slackbot.services.memory.Mem0Memory")
    def test_supports_custom_base_url(self, memory_cls):
        SummaryMemory()
        memory_cls.assert_called_once_with(api_key="secret", base_url="https://mem0.internal")
