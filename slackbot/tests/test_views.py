from __future__ import annotations

from unittest import mock
import os
import tempfile

from django.test import TestCase

from slackbot.models import ConversationSummary
from slackbot.views import SlackEventView, _log_and_download_slack_files


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
        build_prompt.assert_called_once()
        _, kwargs = build_prompt.call_args
        assert "Discussed deployment" in kwargs["context_text"]
        assert kwargs["memories"][0] == "Memory of last deploy"
        summarizer.summarize.assert_called_once()
        slack_client.post_message.assert_called_once_with("C123", "Here is the answer", thread_ts=None)
        assert response == "Here is the answer"


class SlackFileDownloadTests(TestCase):
    @mock.patch("slackbot.views.requests.get")
    @mock.patch("slackbot.views.settings.SLACK_BOT_TOKEN", "x-slack-token")
    def test_downloads_single_file_to_temp_directory(self, _token_patch, mock_get):
        tmpdir = tempfile.mkdtemp()

        event = {
            "files": [
                {
                    "url_private_download": "https://files.slack.com/files-pri/T123/F123/test.txt",
                    "name": "test.txt",
                }
            ]
        }

        response = mock.Mock()
        response.iter_content.return_value = [b"hello ", b"world"]
        response.raise_for_status.return_value = None
        mock_get.return_value = response

        with mock.patch("slackbot.views.SLACK_DOWNLOAD_DIR", tmpdir):
            downloaded = _log_and_download_slack_files(event)

        dest_path = os.path.join(tmpdir, "test.txt")
        assert os.path.exists(dest_path)
        with open(dest_path, "rb") as f:
            assert f.read() == b"hello world"

        assert downloaded is True
        mock_get.assert_called_once()
        called_url = mock_get.call_args[0][0]
        called_headers = mock_get.call_args[1]["headers"]
        assert called_url == "https://files.slack.com/files-pri/T123/F123/test.txt"
        assert called_headers["Authorization"] == "Bearer x-slack-token"

    @mock.patch("slackbot.views.requests.get")
    def test_no_files_does_nothing(self, mock_get):
        downloaded = _log_and_download_slack_files({})
        mock_get.assert_not_called()
        assert downloaded is False


class SlackEventViewDownloadShortCircuitTests(TestCase):
    @mock.patch("slackbot.views.SlackClient")
    @mock.patch("slackbot.views._log_and_download_slack_files")
    def test_app_mention_with_downloaded_file_skips_llm_and_replies_fixed_message(
        self,
        mock_download,
        mock_slack_client_cls,
    ):
        mock_download.return_value = True
        slack_client = mock_slack_client_cls.return_value

        view = SlackEventView.as_view()
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        payload = {
            "type": "event_callback",
            "event_id": "Ev123",
            "event": {
                "type": "app_mention",
                "channel": "C123",
                "ts": "111.222",
                "text": "<@U123> 帮我下载文件",
                "files": [
                    {
                        "id": "F123",
                        "url_private_download": "https://files.slack.com/files-pri/T/F/download/test.txt",
                    }
                ],
            },
        }

        request = factory.post("/api/slack/events/", payload, format="json")
        response = view(request)

        assert response.status_code == 200
        assert response.data["ok"] is True
        assert response.data["downloaded_files"] is True

        mock_download.assert_called_once()
        slack_client.post_message.assert_called_once_with(
            "C123",
            "已成功下载你发的文件，我正在阅读中，稍后再帮你分析。",
            thread_ts="111.222",
        )
