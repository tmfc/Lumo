from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from slackbot.services.slack_client import SlackClient


@mock.patch("slackbot.services.slack_client.WebClient")
@mock.patch("slackbot.services.slack_client.urlopen")
def test_download_shared_files_persists_content(mock_urlopen, webclient_cls):
    mock_response = mock.Mock()
    mock_response.read.return_value = b"hello"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    messages = [
        {
            "files": [
                {
                    "url_private_download": "https://files.slack.com/test",
                    "name": "hello.txt",
                }
            ]
        }
    ]

    with TemporaryDirectory() as tmpdir:
        client = SlackClient(token="xoxb-test")
        saved_files = client.download_shared_files(messages, download_dir=tmpdir)

        saved_path = Path(tmpdir) / "hello.txt"
        assert saved_path.read_bytes() == b"hello"
        assert saved_files == [saved_path]
        mock_urlopen.assert_called_once()
        webclient_cls.assert_called_once_with(token="xoxb-test")
