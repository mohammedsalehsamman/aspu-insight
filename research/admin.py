from django.contrib import admin
from research.models import ResearchPaper, PlagiarismReport


@admin.register(ResearchPaper)
class ResearchPaperAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'author', 'status', 'created_at')
    list_editable = ('status',)
    list_filter = ('status',)
    search_fields = ('title', 'author__email')


@admin.register(PlagiarismReport)
class PlagiarismReportAdmin(admin.ModelAdmin):
    list_display = ('paper', 'total_similarity_score', 'checked_at')
