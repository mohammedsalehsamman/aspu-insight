from django.db import models
from django.conf import settings
from django.core.validators import FileExtensionValidator
from rest_framework.exceptions import ValidationError

from research.validators import validate_file_size

class ResearchPaper(models.Model):
    class Status(models.TextChoices):
        PENDING             = 'pending',             'Pending'
        SUBMITTED           = 'submitted',           'Submitted'
        CHECKING_PLAGIARISM = 'checking_plagiarism', 'Checking Plagiarism'
        EDITOR_REVIEW       = 'editor_review',       'Editor Review'
        REVISION_REQUIRED   = 'revision_required',   'Revision Required'
        COMMITTEE_REVIEW    = 'committee_review',    'Committee Review'
        ACCEPTED            = 'accepted',            'Accepted'
        PUBLISHED           = 'published',           'Published'
        REJECTED            = 'rejected',            'Rejected'
        PLAGIARISM_FAILED   = 'plagiarism_failed',   'Plagiarism Failed'

    title = models.CharField(max_length=255)
    abstract = models.TextField()
    pdf_file = models.FileField(upload_to='papers_pdf/', blank=True, null=True,
                             validators=[validate_file_size, FileExtensionValidator(allowed_extensions=['pdf'])])
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='papers')
    is_paid_open_access = models.BooleanField(default=False)
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    specialization = models.CharField(max_length=32, null=True, blank=False)
    assistant_editor_report = models.TextField(blank=True, null=True)
    is_reviewed_by_assistant = models.BooleanField(default=False)
    review_blindness_type = models.CharField(
        max_length=20,
        choices=[('single_blind', 'Single Blind'), ('double_blind', 'Double Blind'), ('open_review', 'Open Review')],
        default='double_blind'
    )
    assigned_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_papers',
        limit_choices_to={'role': 'editor'},
    )

    class Meta:
        db_table = 'ResearchPaper'

    def str(self):
        return self.title

class PlagiarismReport(models.Model):
    class Status(models.TextChoices):
        COMPLETED = 'completed', 'Completed'
        SKIPPED   = 'skipped',   'Skipped'

    paper = models.OneToOneField(ResearchPaper, on_delete=models.CASCADE, related_name='plagiarism_report')
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.COMPLETED)
    total_similarity_score = models.FloatField(default=0.0)
    internal_similarity_score = models.FloatField(default=0.0)
    external_similarity_score = models.FloatField(default=0.0)
    requires_human_review = models.BooleanField(
        default=False,
        help_text="صحيح إذا وُجد تشابه بمستوى 'مشتبه به' فقط (دون أي تطابق مؤكَّد) — يحتاج مراجعة بشرية قبل القرار"
    )
    ai_keywords = models.JSONField(default=list, blank=True)
    checked_at = models.DateTimeField(auto_now_add=True)

    def str(self):
        return f"Report for {self.paper.title}"

class PlagiarismSource(models.Model):
    class SourceType(models.TextChoices):
        INTERNAL = 'internal', 'Internal (platform corpus)'
        EXTERNAL = 'external', 'External (web/academic search)'

    class ConfidenceLevel(models.TextChoices):
        CONFIRMED = 'confirmed', 'Confirmed match'
        SUSPECTED = 'suspected', 'Suspected paraphrase — needs human review'

    report = models.ForeignKey(PlagiarismReport, on_delete=models.CASCADE, related_name='sources')
    source_type = models.CharField(max_length=10, choices=SourceType.choices, default=SourceType.EXTERNAL)
    confidence_level = models.CharField(
        max_length=10, choices=ConfidenceLevel.choices, default=ConfidenceLevel.CONFIRMED,
        help_text="مؤكَّد (فوق حد الكشف الأساسي) أو مشتبه به (تشابه دلالي متوسط قد يكون إعادة صياغة، يحتاج مراجعة بشرية)"
    )
    matched_paper = models.ForeignKey(
        ResearchPaper, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='plagiarism_matches_as_source'
    )
    source_url = models.URLField(max_length=500, blank=True, default='')
    source_title = models.CharField(max_length=255, blank=True, default='')
    match_percentage = models.FloatField()
    own_text_snippet = models.TextField(default='', help_text="النص من البحث المُقدَّم الذي طابق المصدر")
    source_text_snippet = models.TextField(blank=True, default='', help_text="النص المقابل من المصدر (بحث آخر داخلي، أو ملخص/نص خارجي)")

    def str(self):
        return self.source_title or (self.matched_paper.title if self.matched_paper else 'Unknown source')

class PaperChunkEmbedding(models.Model):
    paper = models.ForeignKey(ResearchPaper, on_delete=models.CASCADE, related_name='chunk_embeddings')
    chunk_index = models.PositiveIntegerField()
    chunk_text = models.TextField()
    embedding_vector = models.JSONField(help_text="متجه النموذج المُضبَط دقيقاً (الأفضل للعربي-عربي)")
    base_embedding_vector = models.JSONField(
        null=True, blank=True,
        help_text="متجه النموذج الأساس (للمقارنات العابرة للغات، عربي↔غير عربي)"
    )
    detected_language = models.CharField(max_length=10, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['chunk_index']

    def str(self):
        return f"Chunk {self.chunk_index} of {self.paper.title}"

class PaperEmbedding(models.Model):
    paper = models.OneToOneField(ResearchPaper, on_delete=models.CASCADE, related_name='embedding')
    embedding_vector = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)

    def str(self):
        return f"Embedding for {self.paper.title}"