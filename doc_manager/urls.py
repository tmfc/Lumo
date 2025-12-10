from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path("", views.DocumentListView.as_view(), name="document-list"),
    path("<int:pk>/", views.DocumentDetailView.as_view(), name="document-detail"),
    path("<int:pk>/reprocess/", views.DocumentReprocessView.as_view(), name="document-reprocess"),
]
