import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound
from committees.models import Committee, CommitteeMember
from research.models import ResearchPaper
from research.service import ResearchPaperService
from notifications.models import Notification
from notifications.services import NotificationService

try:
    from ai_service.services.reviewer_recommendation import AIReviewerMatcherService
except Exception:
    AIReviewerMatcherService = None

logger = logging.getLogger(__name__)

User = get_user_model()

class CommitteeService:

    @staticmethod
    def get_available_reviewers(user, paper_id):
        if getattr(user, 'role', '') != 'editor' and not user.is_staff:
            raise PermissionDenied("غير مصرح لك.")

        try:
            paper = ResearchPaper.objects.get(id=paper_id)
        except ResearchPaper.DoesNotExist:
            raise NotFound("البحث غير موجود.")

        ResearchPaperService.check_assigned_editor(paper, user)

        all_reviewers = User.objects.filter(role='reviewer').exclude(user_id=paper.author_id)

        if AIReviewerMatcherService is not None:
            try:
                ranked_reviewers = AIReviewerMatcherService.rank_reviewers_by_specialization(
                    paper_specialization=paper.specialization,
                    reviewers_queryset=all_reviewers
                )
                if ranked_reviewers:
                    return ranked_reviewers
            except Exception:
                logger.exception(
                    "AI reviewer ranking unavailable for paper %s; falling back to unranked list.",
                    paper_id
                )

        return list(all_reviewers)

    @staticmethod
    def create_committee(user, paper_id, primary_ids, substitute_ids, blinding_type):

        if getattr(user, 'role', '') != 'editor' and not user.is_staff:
            raise PermissionDenied("غير مصرح لك.")

        try:
            paper = ResearchPaper.objects.get(id=paper_id)
        except ResearchPaper.DoesNotExist:
            raise NotFound("البحث غير موجود.")

        ResearchPaperService.check_assigned_editor(paper, user)

        existing = Committee.objects.filter(paper=paper).first()
        if existing:
            if existing.status == 'expired':
                existing.delete()
            else:
                raise ValidationError("اللجنة موجودة مسبقاً.")

        if len(primary_ids) != 3:
            raise ValidationError("يجب 3 محكمين أساسيين.")

        primary_ids = list(map(int, primary_ids))
        substitute_ids = list(map(int, substitute_ids))

        if len(set(primary_ids)) != 3 or len(set(substitute_ids)) != len(substitute_ids):
            raise ValidationError("تكرار محكمين غير مسموح.")

        all_ids = list(set(primary_ids + substitute_ids))
        users = User.objects.filter(user_id__in=all_ids)
        if users.count() != len(all_ids):
            raise ValidationError("يوجد مستخدم غير موجود.")

        for u in users:
            if getattr(u, 'role', '') != 'reviewer':
                raise ValidationError(f"{u.full_name} ليس محكم.")

        with transaction.atomic():
            committee = Committee.objects.create(
                paper=paper,
                editor_id=user.user_id,
                blinding_type=blinding_type,
                status='pending'
            )

            CommitteeMember.objects.bulk_create([
                *[
                    CommitteeMember(
                        committee=committee,
                        user_id=u_id,
                        role='primary',
                        is_substitute=False,
                        is_approved=None
                    )
                    for u_id in primary_ids
                ],
                *[
                    CommitteeMember(
                        committee=committee,
                        user_id=u_id,
                        role='substitute',
                        is_substitute=True,
                        is_approved=None
                    )
                    for u_id in substitute_ids
                ]
            ])

            # bulk_create لا يُطلق post_save إطلاقاً، فالربط هنا يجب أن يكون نداءً صريحاً لا إشارة.
            users_by_id = {u.user_id: u for u in users}
            for u_id in primary_ids + substitute_ids:
                NotificationService.create_notification(
                    recipient=users_by_id[u_id],
                    notification_type=Notification.NotificationType.REVIEWER_ASSIGNED_TO_COMMITTEE,
                    actor=user,
                    target=committee,
                    target_repr=paper.title,
                    context={
                        'paper_title': paper.title,
                        'fallback_title': 'تعيينك في لجنة تحكيم',
                        'fallback_body': f"تم تعيينك محكماً في لجنة تحكيم البحث: {paper.title}",
                    },
                )

        return committee

    @staticmethod
    def handle_reviewer_response(user, member_id, is_approved):
        if getattr(user, 'role', '') != 'reviewer':
            raise PermissionDenied()

        try:
            member = CommitteeMember.objects.select_related('committee').get(
                id=member_id,
                user=user
            )
        except CommitteeMember.DoesNotExist:
            raise NotFound()

        with transaction.atomic():
            committee = Committee.objects.select_for_update().get(
                id=member.committee_id
            )

            if committee.status in Committee.FINAL_STATUSES:
                raise ValidationError("القرار النهائي صدر، لا يمكن تغيير الرد.")

            if member.is_approved == is_approved:
                raise ValidationError("الرد نفسه مسجَّل مسبقاً.")

            previously_accepted = member.is_approved is True
            member.is_approved = is_approved

            if is_approved is False:
                member.response = 'declined'

                if previously_accepted:

                    member.paper_decision = 'pending'

                    if committee.status == 'approved':
                        committee.status = 'pending'
                        committee.save()

                    substitute = CommitteeMember.objects.filter(
                        committee=committee,
                        is_substitute=True,
                        is_approved=None
                    ).first()
                    if substitute:
                        NotificationService.create_notification(
                            recipient=substitute.user,
                            notification_type=Notification.NotificationType.REVIEWER_ASSIGNED_TO_COMMITTEE,
                            target=committee,
                            target_repr=committee.paper.title,
                            context={
                                'paper_title': committee.paper.title,
                                'fallback_title': 'دعوة للانضمام كمحكم بديل',
                                'fallback_body': f"أحد الأعضاء اعتذر، وأنت مرشح كعضو بديل في لجنة تحكيم البحث: {committee.paper.title}",
                            },
                        )
                member.save()

            elif is_approved is True:
                member.response = 'accepted'

                if member.is_substitute:
                    member.is_substitute = False
                    member.role = 'primary'

                member.save()

                approved_count = CommitteeMember.objects.filter(
                    committee=committee,
                    is_substitute=False,
                    is_approved=True
                ).count()

                if approved_count == 3:
                    committee.status = 'approved'
                    committee.save()

        return member

    @staticmethod
    def get_committee_invitation(user, member_id):
        if getattr(user, 'role', '') != 'reviewer':
            raise PermissionDenied()

        try:
            member = CommitteeMember.objects.select_related('committee', 'committee__paper').get(
                id=member_id,
                user=user
            )
        except CommitteeMember.DoesNotExist:
            raise NotFound()

        return member

    @staticmethod
    def get_my_invitations(user):
        if getattr(user, 'role', '') != 'reviewer':
            raise PermissionDenied()

        return CommitteeMember.objects.filter(
            user=user
        ).select_related('committee', 'committee__paper').order_by('-assigned_at')

    @staticmethod
    def submit_review_decision(user, member_id, decision, comment):
        if getattr(user, 'role', '') != 'reviewer':
            raise PermissionDenied()

        VALID = ['accept_paper', 'reject_paper', 'modify_paper']

        try:
            member = CommitteeMember.objects.select_related('committee').get(
                id=member_id,
                user=user
            )
        except CommitteeMember.DoesNotExist:
            raise NotFound()

        if member.committee.status != 'approved':
            raise ValidationError("اللجنة غير جاهزة.")

        if decision not in VALID:
            raise ValidationError("قرار غير صالح.")

        with transaction.atomic():
            member.paper_decision = decision
            member.comments = comment
            member.save()

            all_members = CommitteeMember.objects.filter(
                committee=member.committee,
                is_substitute=False
            )

            total = all_members.count()

            voted = all_members.filter(
                paper_decision__in=VALID
            )

            if voted.count() != total:
                return

            accept = voted.filter(paper_decision='accept_paper').count()
            reject = voted.filter(paper_decision='reject_paper').count()

            committee = member.committee

            if accept >= 2:
                committee.status = 'accepted'
            elif reject >= 2:
                committee.status = 'rejected'
            else:
                committee.status = 'revision'

            committee.save()
            CommitteeService._notify_committee_decision(committee, actor=user)

    @staticmethod
    def _notify_committee_decision(committee, actor=None):
        for recipient in {committee.paper.author, committee.editor}:
            NotificationService.create_notification(
                recipient=recipient,
                notification_type=Notification.NotificationType.COMMITTEE_REVIEW_RECEIVED,
                actor=actor,
                target=committee,
                target_repr=committee.paper.title,
                context={
                    'paper_title': committee.paper.title,
                    'committee_status': committee.status,
                    'fallback_title': 'قرار لجنة التحكيم',
                    'fallback_body': f"صدر قرار لجنة تحكيم البحث: {committee.paper.title}.",
                },
            )

    @staticmethod
    def _try_force_decision(committee):
        members = CommitteeMember.objects.filter(
            committee=committee,
            is_substitute=False
        )
        voted = members.exclude(paper_decision='pending')

        accept = voted.filter(paper_decision='accept_paper').count()
        reject = voted.filter(paper_decision='reject_paper').count()
        modify = voted.filter(paper_decision='modify_paper').count()

        if accept >= 2:
            committee.status = 'accepted'
        elif reject >= 2:
            committee.status = 'rejected'
        elif modify >= 2:
            committee.status = 'revision'
        else:
            return False

        committee.save()
        CommitteeService._notify_committee_decision(committee)
        return True

    @staticmethod
    def expire_overdue_committees():
        from django.utils import timezone
        overdue = Committee.objects.filter(
            deadline__lt=timezone.now(),
            status__in=['pending', 'approved']
        ).select_related('editor', 'paper')

        for committee in overdue:
            with transaction.atomic():
                committee = Committee.objects.select_for_update().get(pk=committee.pk)
                if committee.status not in ('pending', 'approved'):
                    continue
                if not CommitteeService._try_force_decision(committee):
                    committee.status = 'expired'
                    committee.save()
                    NotificationService.create_notification(
                        recipient=committee.editor,
                        notification_type=Notification.NotificationType.COMMITTEE_DEADLINE_EXPIRED,
                        target=committee,
                        target_repr=committee.paper.title,
                        level=Notification.Level.WARNING,
                        context={
                            'paper_title': committee.paper.title,
                            'deadline_days': getattr(settings, 'COMMITTEE_DEADLINE_DAYS', 15),
                            'fallback_title': 'انتهت مهلة اللجنة',
                            'fallback_body': (
                                f"انتهت مهلة لجنة تحكيم البحث \"{committee.paper.title}\" بلا قرار نهائي. "
                                "يمكنك تعيين لجنة جديدة."
                            ),
                        },
                    )

    @staticmethod
    def get_research_paper_details(user, paper_id):
        try:
            paper = ResearchPaper.objects.select_related('author').get(id=paper_id)
        except ResearchPaper.DoesNotExist:
            raise NotFound("Research paper not found")

        allowed = (
            user.is_staff
            or user == paper.author
            or getattr(user, 'role', '') == 'admin'
            or paper.assigned_editor_id == getattr(user, 'user_id', None)
            or Committee.objects.filter(paper=paper, editor=user).exists()
            or CommitteeMember.objects.filter(committee__paper=paper, user=user).exists()
        )
        if not allowed:
            raise PermissionDenied("غير مصرح لك بعرض تفاصيل هذا البحث.")

        from configuration.security import can_user_access_pdf
        is_blinded = not can_user_access_pdf(user, paper)

        author_name = "Anonymous Author (Hidden for Committee Review)"
        if user.is_authenticated:
            if user == paper.author or user.is_staff or getattr(user, 'role', '') == 'editor':
                author_name = paper.author.get_full_name() if hasattr(paper.author, 'get_full_name') else str(paper.author)

        pdf_url = None
        if user.is_authenticated:
            if user == paper.author or user.is_staff or getattr(user, 'role', '') == 'editor' or not is_blinded:
                pdf_url = paper.pdf_file.url if paper.pdf_file else None

        response_data = {
            "id": paper.id,
            "title": paper.title,
            "abstract": paper.abstract,
            "is_paid_open_access": paper.is_paid_open_access,
            "pdf_file": pdf_url,
            "author_name": author_name,
            "status": paper.status,
            "rejection_reason": paper.rejection_reason,
            "created_at": paper.created_at.isoformat() if paper.created_at else None
        }

        return response_data, is_blinded
