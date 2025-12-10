"""URL configuration for application."""
from django.contrib import admin
from django.urls import include, path

from doc_manager.views import AuthLoginView, AuthLogoutView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("slackbot.urls")),
    path("api/documents/", include("doc_manager.urls")),
    path("api/auth/login/", AuthLoginView.as_view(), name="auth-login"),
    path("api/auth/logout/", AuthLogoutView.as_view(), name="auth-logout"),
]
