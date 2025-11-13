from django.test import TestCase

from slackbot.services.summarizer import build_summary_prompt


class BuildSummaryPromptTests(TestCase):
    def test_renders_messages(self):
        prompt = build_summary_prompt(
            [
                {"user": "U1", "text": "Hello", "ts": "1"},
                {"user": "U2", "text": "World", "ts": "2"},
            ],
            scope_description="thread",
        )
        self.assertIn("thread", prompt)
        self.assertIn("U1", prompt)
        self.assertIn("World", prompt)
