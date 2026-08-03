from django.db import migrations

# قوالب in_app بالعربية لكل نوع إشعار فعّال حالياً (تُستخدم في Phase 1 وتُغطي مسبقاً
# محفزات Phase 2 مثل قرارات اللجنة والمواعيد). قوالب البريد/الإنجليزية تُضاف لاحقاً
# دون الحاجة لتعديل هذه الهجرة.
TEMPLATES = [
    ('paper_submitted', 'بحث جديد بانتظار المراجعة', 'البحث "{{ paper_title }}" أصبح جاهزاً لمراجعة مساعد المحرر.'),
    ('paper_status_changed', 'تحديث حالة البحث', 'تغيّرت حالة البحث "{{ paper_title }}" من {{ from_status }} إلى {{ to_status }}.'),
    ('paper_published', 'تم نشر بحثك', 'تهانينا! تم نشر البحث "{{ paper_title }}".'),
    ('assistant_review_received', 'مراجعة مساعد المحرر', 'تمت مراجعة البحث "{{ paper_title }}" من قبل مساعد المحرر.'),
    ('editor_review_received', 'مراجعة المحرر', 'تمت مراجعة البحث "{{ paper_title }}" من قبل المحرر.'),
    ('committee_review_received', 'قرار لجنة التحكيم', 'صدر قرار لجنة التحكيم بخصوص البحث "{{ paper_title }}".'),
    ('committee_deadline_approaching', 'اقتراب موعد اللجنة', 'يقترب الموعد النهائي لمراجعة لجنة تحكيم البحث "{{ paper_title }}".'),
    ('committee_deadline_expired', 'انتهاء مهلة اللجنة', 'انتهت المهلة المحددة للجنة تحكيم البحث "{{ paper_title }}".'),
    ('editor_assigned', 'تعيينك محرراً لبحث', 'تم تعيينك محرراً مسؤولاً عن البحث "{{ paper_title }}".'),
    ('reviewer_assigned_to_committee', 'تعيينك في لجنة تحكيم', 'تم تعيينك محكماً في لجنة تحكيم البحث "{{ paper_title }}".'),
    ('role_changed', 'تغيّرت صلاحيتك', 'تم تغيير صلاحيتك من {{ old_role }} إلى {{ new_role }}.'),
    ('system_announcement', 'إعلان من الإدارة', '{{ body }}'),
]


def seed_templates(apps, schema_editor):
    NotificationTemplate = apps.get_model('notifications', 'NotificationTemplate')
    for notification_type, subject, body in TEMPLATES:
        NotificationTemplate.objects.update_or_create(
            notification_type=notification_type, channel='in_app', language='ar',
            defaults={'subject_template': subject, 'body_template': body, 'is_active': True},
        )


def remove_templates(apps, schema_editor):
    NotificationTemplate = apps.get_model('notifications', 'NotificationTemplate')
    types = [t[0] for t in TEMPLATES]
    NotificationTemplate.objects.filter(
        notification_type__in=types, channel='in_app', language='ar',
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_templates, remove_templates),
    ]
