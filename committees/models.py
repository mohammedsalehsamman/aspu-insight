from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

class Committee(models.Model):
    BLINDING_CHOICES = [
        ('open', 'مفتوح'),
        ('single_blind', 'تعمية أحادية'),
        ('double_blind', 'تعمية ثنائية'),
    ]
    STATUS_CHOICES = [
        ('pending', 'قيد التشكيل'),
        ('approved', 'تمت الموافقة على اللجنة'),
        ('accepted', 'تمت الموافقة على الورقة'),
        ('rejected', 'مرفوضة'),
        ('revision', 'مطلوب تعديلات'),
        ('expired', 'منتهية الصلاحية'),
    ]

    FINAL_STATUSES = {'accepted', 'rejected', 'revision', 'expired'}

    paper = models.OneToOneField('research.ResearchPaper', on_delete=models.CASCADE, related_name='committee')
    editor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_committees')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    blinding_type = models.CharField(max_length=20, choices=BLINDING_CHOICES, default='single_blind')
    created_at = models.DateTimeField(auto_now_add=True)
    deadline = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'Committee'

    def save(self, *args, **kwargs):
        if not self.pk and not self.deadline:
            days = getattr(settings, 'COMMITTEE_DEADLINE_DAYS', 15)
            self.deadline = timezone.now() + timedelta(days=days)
        super().save(*args, **kwargs)

class CommitteeMember(models.Model):
    ROLE_CHOICES = [
        ('primary', 'أساسي'),
        ('substitute', 'بديل'),
    ]
    RESPONSE_CHOICES = [
        ('pending', 'بانتظار الرد'),
        ('accepted', 'وافق'),
        ('declined', 'اعتذر'),
    ]
    DECISION_CHOICES = [
        ('pending', 'قيد الدراسة'),
        ('accept_paper', 'قبول الورقة'),
        ('reject_paper', 'رفض الورقة'),
        ('modify_paper', 'طلب تعديلات'),
    ]
    committee = models.ForeignKey(Committee, on_delete=models.CASCADE, related_name='committee_assigned_members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='user_committee_memberships')
    role = models.CharField(max_length=15, choices=ROLE_CHOICES)
    response = models.CharField(max_length=15, choices=RESPONSE_CHOICES, default='pending')
    paper_decision = models.CharField(max_length=15, choices=DECISION_CHOICES, default='pending')
    comments = models.TextField(blank=True, null=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    is_substitute = models.BooleanField(default=False)
    is_approved = models.BooleanField(null=True, blank=True, default=None)

    class Meta:
        db_table = 'CommitteeMember'
        unique_together = ('committee', 'user')