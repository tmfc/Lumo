from django.contrib import admin

from .models import ConversationSummary


@admin.register(ConversationSummary)
class ConversationSummaryAdmin(admin.ModelAdmin):
    list_display = ("target_type", "target_id", "generated_for", "model_used", "created_at")
    search_fields = ("target_id", "summary_text")
    list_filter = ("target_type", "model_used")
