from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound
from committees.models import Committee, CommitteeMember
from research.models import ResearchPaper

User = get_user_model()


class CommitteeService:

    @staticmethod
    def create_committee(user, paper_id, primary_ids, substitute_ids, blinding_type):

        if getattr(user, 'role', '') != 'editor' and not user.is_staff:
            raise PermissionDenied("غير مصرح لك.")

        try:
            paper = ResearchPaper.objects.get(id=paper_id)
        except ResearchPaper.DoesNotExist:
            raise NotFound("البحث غير موجود.")

        if Committee.objects.filter(paper=paper).exists():
            raise ValidationError("اللجنة موجودة مسبقاً.")

        if len(primary_ids) != 3:
            raise ValidationError("يجب 3 محكمين أساسيين.")

        primary_ids = list(map(int, primary_ids))
        substitute_ids = list(map(int, substitute_ids))

        # ❌ منع التكرار
        if len(set(primary_ids)) != 3 or len(set(substitute_ids)) != len(substitute_ids):
            raise ValidationError("تكرار محكمين غير مسموح.")

        all_ids = list(set(primary_ids + substitute_ids))

        # ✅ FIX مهم جداً: user_id بدل id
        users = User.objects.filter(user_id__in=all_ids)

        if users.count() != len(all_ids):
            raise ValidationError("يوجد مستخدم غير موجود.")

        for u in users:
            if getattr(u, 'role', '') != 'reviewer':
                raise ValidationError(f"{u.full_name} ليس محكم.")

        with transaction.atomic():
            committee = Committee.objects.create(
                paper=paper,
                editor_id=user.user_id,   # ✅ FIX
                blinding_type=blinding_type,
                status='pending'
            )

            CommitteeMember.objects.bulk_create([
                *[
                    CommitteeMember(
                        committee=committee,
                        user_id=u_id,  # لازم يكون user_id الحقيقي
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

        return committee

    # =====================================================

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

        if member.is_approved is not None:
            raise ValidationError("تم الرد مسبقاً.")

        with transaction.atomic():

            committee = Committee.objects.select_for_update().get(
                id=member.committee_id
            )

            member.is_approved = is_approved
            member.save()

            approved_count = CommitteeMember.objects.filter(
                committee=committee,
                is_substitute=False,
                is_approved=True
            ).count()

            if approved_count == 3:
                committee.status = 'approved'
                committee.save()

            elif is_approved is False:
                committee.status = 'rejected'
                committee.save()

        return member

    # =====================================================

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

            # ❗ مهم: لا تنفذ القرار قبل اكتمال التصويت
            if voted.count() != total:
                return

            accept = voted.filter(paper_decision='accept_paper').count()
            reject = voted.filter(paper_decision='reject_paper').count()
            modify = voted.filter(paper_decision='modify_paper').count()

            committee = member.committee

            if accept >= 2:
                committee.status = 'accepted'
            elif reject >= 2:
                committee.status = 'rejected'
            else:
                committee.status = 'revision'

            committee.save()

   

    @staticmethod
    def get_research_paper_details(user, paper_id):
        from research.models import ResearchPaper
        from rest_framework.exceptions import NotFound
        
        try:
            paper = ResearchPaper.objects.select_related('author').get(id=paper_id)
        except ResearchPaper.DoesNotExist:
            raise NotFound("Research paper not found")

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