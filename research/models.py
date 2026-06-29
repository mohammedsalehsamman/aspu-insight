from django.db import models
from django.conf import settings

class ResearchPaper(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('checking_plagiarism', 'Checking Plagiarism'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('plagiarism_failed', 'Plagiarism Failed')
    ]
    title = models.CharField(max_length=255)
    abstract = models.TextField()
    pdf_file = models.FileField(upload_to='papers_pdf/', blank=True, null=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='papers')
    is_paid_open_access = models.BooleanField(default=False)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='pending')
    rejection_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    assistant_editor_report = models.TextField(blank=True, null=True)
    is_reviewed_by_assistant = models.BooleanField(default=False)
    review_blindness_type = models.CharField(
        max_length=20, 
        choices=[('single_blind', 'Single Blind'), ('double_blind', 'Double Blind'), ('open_review', 'Open Review')], 
        default='double_blind'
    )

    class Meta:
        db_table = 'ResearchPaper'

    def str(self):
        return self.title

class PlagiarismReport(models.Model):
    paper = models.OneToOneField(ResearchPaper, on_delete=models.CASCADE, related_name='plagiarism_report')
    total_similarity_score = models.FloatField()
    ai_keywords = models.JSONField(default=list, blank=True)
    checked_at = models.DateTimeField(auto_now_add=True)

class PlagiarismSource(models.Model):
    report = models.ForeignKey(PlagiarismReport, on_delete=models.CASCADE, related_name='sources')
    source_url = models.URLField(max_length=500)
    source_title = models.CharField(max_length=255)
    match_percentage = models.FloatField()
    matched_text_snippet = models.TextField()