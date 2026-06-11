from django.contrib import admin

from editorReview.models import EditorReview


@admin.register(EditorReview)
class EditorReviewAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'paper', 'editor', 'stage', 'decision',
        'language_review_passed', 'citation_check_passed',
        'publisher_permission_obtained', 'reviewed_at',
    ]
    list_filter = ['stage', 'decision']
    search_fields = ['paper__title', 'editor__email']
    readonly_fields = ['reviewed_at', 'updated_at']
    ordering = ['-reviewed_at']
