from django.test import TestCase

from slackbot.services.summarizer import build_question_prompt, build_summary_prompt


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


class BuildQuestionPromptTests(TestCase):
    def test_includes_context_and_memories(self):
        prompt = build_question_prompt(
            question="What shipped today?",
            context_text="[1] U1: Release planning",
            memories=["Yesterday's summary", "Pending QA"],
        )
        self.assertIn("What shipped today?", prompt)
        self.assertIn("Release planning", prompt)
        self.assertIn("Yesterday's summary", prompt)
