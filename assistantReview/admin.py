from django.contrib import admin

from assistantReview.models import AssistantReview


@admin.register(AssistantReview)
class AssistantReviewAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'paper', 'assistant', 'decision',
        'recommended_decision', 'is_format_compliant',
        'is_complete', 'reviewed_at',
    ]
    list_filter = [
        'decision', 'recommended_decision',
        'is_format_compliant', 'is_complete',
    ]
    search_fields = ['paper__title', 'assistant__email']
    filter_horizontal = ['suggested_reviewers']
    readonly_fields = ['reviewed_at', 'updated_at']
    ordering = ['-reviewed_at']
