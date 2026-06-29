from django.core.mail import send_mail
from django.conf import settings


def send_committee_expiry_email(committee):
    editor = committee.editor
    paper = committee.paper
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    paper_url = f"{frontend_url}/papers/{paper.id}"

    send_mail(
        subject='انتهت مدة اللجنة المتخصصة - مطلوب إجراء',
        message=(
            f"عزيزي {editor.full_name}،\n\n"
            f"انتهت مدة اللجنة المتخصصة المعيّنة للورقة البحثية:\n"
            f"العنوان: {paper.title}\n\n"
            f"لم يصدر قرار نهائي خلال المدة المحددة ({getattr(settings, 'COMMITTEE_DEADLINE_DAYS', 15)} يوماً).\n"
            f"يمكنك الآن تعيين لجنة جديدة من خلال الرابط التالي:\n"
            f"{paper_url}\n\n"
            "فريق ASPU Insight"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[editor.email],
        fail_silently=True,
    )


def send_substitute_invitation_email(member):
    reviewer = member.user
    paper = member.committee.paper
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    paper_url = f"{frontend_url}/papers/{paper.id}"

    send_mail(
        subject='طلب انضمام إلى لجنة تحكيم - بديل',
        message=(
            f"عزيزي {reviewer.full_name}،\n\n"
            f"تمت دعوتك للانضمام إلى لجنة تحكيم الورقة البحثية:\n"
            f"العنوان: {paper.title}\n\n"
            f"أحد الأعضاء الأساسيين اعتذر عن المشاركة، وأنت مرشح كعضو بديل.\n"
            f"يرجى الرد على الطلب من خلال الرابط التالي:\n"
            f"{paper_url}\n\n"
            "فريق ASPU Insight"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[reviewer.email],
        fail_silently=True,
    )
