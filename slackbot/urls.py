from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("diagnostics/", views.DiagnosticsView.as_view(), name="diagnostics"),
    path("slack/events/", views.SlackEventView.as_view(), name="slack-events"),
    path("summaries/channel/", views.ChannelSummaryView.as_view(), name="channel-summary"),
    path("summaries/thread/", views.ThreadSummaryView.as_view(), name="thread-summary"),
]
