from django.contrib import admin
from django.utils.html import format_html
from .models import IEEECheckReport


@admin.register(IEEECheckReport)
class IEEECheckReportAdmin(admin.ModelAdmin):
    list_display  = [
        'id', 'paper_title_short', 'detected_language',
        'total_references', 'score_badge', 'status_badge',
        'created_at',
    ]
    list_filter   = ['status', 'detected_language', 'created_at']
    search_fields = ['paper_title', 'original_filename']
    readonly_fields = [
        'paper_title', 'detected_language', 'total_pages',
        'total_citations_in_text', 'total_references',
        'missing_citations_count', 'unused_references_count',
        'overall_score', 'citation_matching_score', 'format_score',
        'crossref_score', 'crossref_checked', 'crossref_verified',
        'status', 'summary', 'full_result',
        'processing_time_seconds', 'created_at',
    ]
    ordering = ['-created_at']

    def paper_title_short(self, obj):
        return obj.paper_title[:60] or obj.original_filename
    paper_title_short.short_description = 'الورقة'

    def score_badge(self, obj):
        score = obj.overall_score
        color = '#27ae60' if score >= 75 else '#e67e22' if score >= 50 else '#e74c3c'
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:4px;">{}/100</span>',
            color, score,
        )
    score_badge.short_description = 'الدرجة'

    def status_badge(self, obj):
        icons = {'pass': 'مقبول', 'warning': 'يحتاج تحسين', 'fail': 'يحتاج مراجعة', 'error': 'خطأ'}
        return icons.get(obj.status, obj.status)
    status_badge.short_description = 'الحالة'
