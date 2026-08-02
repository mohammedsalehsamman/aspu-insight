from django.db import migrations

# نفس أنواع migration 0004 (المفعّلة افتراضياً على قناة email) — نصوص أقصر تناسب إشعار جوال
# (subject_template هنا هو عنوان الإشعار، body_template نصه، لا "موضوع بريد").
TEMPLATES = [
    ('paper_published', 'تم نشر بحثك', 'بحثك "{{ paper_title }}" نُشر رسمياً في ASPU Insight.'),
    ('committee_review_received', 'قرار لجنة التحكيم', 'صدر قرار بخصوص البحث "{{ paper_title }}".'),
    (
        'committee_deadline_approaching', 'اقتراب موعد اللجنة',
        'يقترب الموعد النهائي للجنة تحكيم "{{ paper_title }}".',
    ),
    (
        'committee_deadline_expired', 'انتهت مهلة اللجنة',
        'انتهت مهلة لجنة تحكيم "{{ paper_title }}" دون قرار نهائي.',
    ),
    ('reviewer_assigned_to_committee', 'دعوة لجنة تحكيم', 'دُعيت للانضمام إلى لجنة تحكيم "{{ paper_title }}".'),
    ('system_announcement', 'إعلان من الإدارة', '{{ body }}'),
]


def seed_templates(apps, schema_editor):
    NotificationTemplate = apps.get_model('notifications', 'NotificationTemplate')
    for notification_type, title, body in TEMPLATES:
        NotificationTemplate.objects.update_or_create(
            notification_type=notification_type, channel='push', language='ar',
            defaults={'subject_template': title, 'body_template': body, 'is_active': True},
        )


def remove_templates(apps, schema_editor):
    NotificationTemplate = apps.get_model('notifications', 'NotificationTemplate')
    types = [t[0] for t in TEMPLATES]
    NotificationTemplate.objects.filter(
        notification_type__in=types, channel='push', language='ar',
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0005_notificationdelivery_device_token'),
    ]

    operations = [
        migrations.RunPython(seed_templates, remove_templates),
    ]
