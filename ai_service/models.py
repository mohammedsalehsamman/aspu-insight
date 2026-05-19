from django.db import models
from django.conf import settings


class IEEECheckReport(models.Model):

    class Status(models.TextChoices):
        PENDING = 'pending', 'قيد المعالجة'
        PASS    = 'pass',    'مقبول'
        WARNING = 'warning', 'يحتاج تحسين'
        FAIL    = 'fail',    'يحتاج مراجعة'
        ERROR   = 'error',   'خطأ في المعالجة'

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='ieee_reports',
        verbose_name='طُلب من قِبل',
    )

    pdf_file = models.FileField(
        upload_to='ieee_documents/%Y/%m/',
        verbose_name='ملف البحث (PDF/DOCX)',
    )
    original_filename = models.CharField(max_length=255, blank=True, verbose_name='اسم الملف الأصلي')

    paper_title       = models.CharField(max_length=500, blank=True, verbose_name='عنوان الورقة')
    detected_language = models.CharField(max_length=10,  blank=True, verbose_name='اللغة المكتشفة')
    total_pages       = models.PositiveIntegerField(default=0, verbose_name='عدد الصفحات')

    total_citations_in_text  = models.PositiveIntegerField(default=0, verbose_name='الاستشهادات في النص')
    total_references         = models.PositiveIntegerField(default=0, verbose_name='إجمالي المراجع')
    missing_citations_count  = models.PositiveIntegerField(default=0, verbose_name='استشهادات بدون مراجع')
    unused_references_count  = models.PositiveIntegerField(default=0, verbose_name='مراجع غير مُستخدمة')

    citation_matching_score = models.FloatField(default=0.0, verbose_name='درجة تطابق الاستشهادات')
    format_score            = models.FloatField(default=0.0, verbose_name='درجة التنسيق')
    crossref_score          = models.FloatField(default=0.0, verbose_name='درجة Crossref')
    overall_score           = models.FloatField(default=0.0, verbose_name='الدرجة الكلية')

    status  = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, verbose_name='الحالة')
    summary = models.TextField(blank=True, verbose_name='الملخص')

    full_result = models.JSONField(default=dict, verbose_name='النتيجة الكاملة')

    crossref_checked  = models.PositiveIntegerField(default=0, verbose_name='DOIs تم التحقق منها')
    crossref_verified = models.PositiveIntegerField(default=0, verbose_name='DOIs صحيحة')

    created_at              = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    processing_time_seconds = models.FloatField(null=True, blank=True, verbose_name='وقت المعالجة (ثانية)')

    class Meta:
        verbose_name        = 'تقرير IEEE'
        verbose_name_plural = 'تقارير IEEE'
        ordering            = ['-created_at']

    def __str__(self) -> str:
        return f"[{self.status.upper()}] {self.paper_title[:50]} — {self.overall_score}/100"

    @property
    def status_display_ar(self) -> str:
        return {
            'pass':    ' مقبول',
            'warning': ' يحتاج تحسين',
            'fail':    ' يحتاج مراجعة',
            'pending': ' قيد المعالجة',
            'error':   ' خطأ',
        }.get(self.status, self.status)

    @property
    def recommendations(self) -> list:
        return self.full_result.get('recommendations', [])

    @property
    def references_list(self) -> list:
        return self.full_result.get('references', [])
