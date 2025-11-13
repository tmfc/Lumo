"""URL configuration for lumobot."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("slackbot.urls")),
]
