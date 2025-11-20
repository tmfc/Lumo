from __future__ import annotations

from unittest import mock

from django.test import TestCase

from slackbot.models import ConversationSummary
from slackbot.views import SlackEventView


class SlackEventViewQuestionTests(TestCase):
    @mock.patch("slackbot.views.build_question_prompt")
    @mock.patch("slackbot.views.Summarizer")
    @mock.patch("slackbot.views.SlackClient")
    def test_answers_question_using_context_and_memory(
        self,
        slack_client_cls,
        summarizer_cls,
        build_prompt,
    ):
        event = {"channel": "C123", "text": "What changed?"}
        slack_client = slack_client_cls.return_value
        slack_client.fetch_channel_messages.return_value = [
            {"user": "U1", "text": "Discussed deployment", "ts": "1"}
        ]
        summarizer = summarizer_cls.return_value
        summarizer.summarize.return_value = "Here is the answer"
        build_prompt.return_value = "prompt"

        ConversationSummary.objects.create(
            target_type=ConversationSummary.TargetType.CHANNEL,
            target_id="C123",
            summary_text="Memory of last deploy",
        )

        view = SlackEventView()
        response = view._handle_app_mention(event)

        slack_client.fetch_channel_messages.assert_called_once()
        slack_client.download_shared_files.assert_called_once()
        build_prompt.assert_called_once()
        _, kwargs = build_prompt.call_args
        assert "Discussed deployment" in kwargs["context_text"]
        assert kwargs["memories"][0] == "Memory of last deploy"
        summarizer.summarize.assert_called_once()
        slack_client.post_message.assert_called_once_with("C123", "Here is the answer", thread_ts=None)
        assert response == "Here is the answer"


class SlackEventViewFileDownloadTests(TestCase):
    @mock.patch("slackbot.views.Summarizer")
    @mock.patch("slackbot.views.SlackClient")
    def test_downloads_files_shared_in_event(self, slack_client_cls, summarizer_cls):
        slack_client = slack_client_cls.return_value
        slack_client.fetch_channel_messages.return_value = []

        summarizer = summarizer_cls.return_value
        summarizer.summarize.return_value = "summary"
        summarizer.model = "test-model"

        event = {
            "channel": "C456",
            "text": "summary please",
            "files": [{"url_private_download": "https://files.slack.com/test", "name": "doc.txt"}],
        }

        view = SlackEventView()
        view._handle_app_mention(event)

        slack_client.download_shared_files.assert_called_once_with([{"files": event["files"]}])
        summarizer.summarize.assert_called_once()
