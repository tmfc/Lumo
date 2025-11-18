"""Serializers that validate Slack payloads."""
from __future__ import annotations

from datetime import date

from rest_framework import serializers


class SlackEventSerializer(serializers.Serializer):
    type = serializers.CharField()
    challenge = serializers.CharField(required=False)
    # Slack's `event` field can contain nested objects, arrays and non-string values,
    # so we accept arbitrary JSON here instead of restricting all values to strings.
    event = serializers.DictField(required=False)


class ChannelSummarySerializer(serializers.Serializer):
    channel_id = serializers.CharField()
    date = serializers.DateField(required=False)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    max_messages = serializers.IntegerField(required=False, min_value=1)
    mem0_user_id = serializers.CharField(required=False)

    def validate(self, attrs):  # pragma: no cover - simple validation
        start = attrs.get("start_date")
        end = attrs.get("end_date")
        if start and end and start > end:
            raise serializers.ValidationError("start_date must be before end_date")
        return attrs

    def get_target_date(self) -> date | None:
        return self.validated_data.get("date")


class ThreadSummarySerializer(serializers.Serializer):
    channel_id = serializers.CharField()
    thread_ts = serializers.CharField(help_text="Slack thread timestamp")
    max_messages = serializers.IntegerField(required=False, min_value=1)
    mem0_user_id = serializers.CharField(required=False)
