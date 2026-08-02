from django.db import migrations

# قوالب البريد الإلكتروني بالعربية — فقط للأنواع المفعّلة افتراضياً على قناة email
# (راجع DEFAULT_CHANNELS_BY_TYPE في notifications/services.py).
TEMPLATES = [
    (
        'paper_published', 'تهانينا! تم نشر بحثك في ASPU Insight',
        'عزيزي الباحث،\n\nيسعدنا إبلاغك بأن بحثك "{{ paper_title }}" قد نُشر رسمياً في المجلة.\n\nفريق ASPU Insight',
    ),
    (
        'committee_review_received', 'قرار لجنة التحكيم بخصوص بحثك',
        'صدر قرار لجنة التحكيم بخصوص البحث "{{ paper_title }}".\n\nيمكنك متابعة التفاصيل من لوحة التحكم.\n\nفريق ASPU Insight',
    ),
    (
        'committee_deadline_approaching', 'تذكير: اقتراب موعد لجنة التحكيم',
        'يقترب الموعد النهائي لمراجعة لجنة تحكيم البحث "{{ paper_title }}" ({{ deadline }}).\n\nفريق ASPU Insight',
    ),
    (
        'committee_deadline_expired', 'انتهت مهلة اللجنة المتخصصة - مطلوب إجراء',
        (
            'انتهت مهلة اللجنة المتخصصة المعيّنة للبحث "{{ paper_title }}" ({{ deadline_days }} يوماً) '
            'دون صدور قرار نهائي.\nيمكنك الآن تعيين لجنة جديدة من لوحة التحكم.\n\nفريق ASPU Insight'
        ),
    ),
    (
        'reviewer_assigned_to_committee', 'دعوة للانضمام إلى لجنة تحكيم',
        'تمت دعوتك للانضمام إلى لجنة تحكيم البحث "{{ paper_title }}".\n\nيرجى الرد من خلال لوحة التحكم.\n\nفريق ASPU Insight',
    ),
    (
        'system_announcement', 'إعلان من إدارة ASPU Insight',
        '{{ body }}\n\nفريق ASPU Insight',
    ),
]


def seed_templates(apps, schema_editor):
    NotificationTemplate = apps.get_model('notifications', 'NotificationTemplate')
    for notification_type, subject, body in TEMPLATES:
        NotificationTemplate.objects.update_or_create(
            notification_type=notification_type, channel='email', language='ar',
            defaults={'subject_template': subject, 'body_template': body, 'is_active': True},
        )


def remove_templates(apps, schema_editor):
    NotificationTemplate = apps.get_model('notifications', 'NotificationTemplate')
    types = [t[0] for t in TEMPLATES]
    NotificationTemplate.objects.filter(
        notification_type__in=types, channel='email', language='ar',
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0003_notificationdelivery_rendered_body_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_templates, remove_templates),
    ]
