<<<<<<< HEAD
import os
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

=======
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound
>>>>>>> 8009729a235f7b93b8bdf2dd63e85d842a3aade5
from committees.models import Committee, CommitteeMember
from committees.utils import send_committee_expiry_email, send_substitute_invitation_email
from research.models import ResearchPaper

User = get_user_model()


<<<<<<< HEAD
class AIReviewerMatcherService:
    _model = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            model_path = r"C:\Users\hp\Desktop\aspuinsight\aspu-insight\my-model"
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"Could not find model directory at: {model_path}")
            cls._model = SentenceTransformer(model_path, local_files_only=True)
        return cls._model

    @classmethod
    def rank_reviewers_by_specialization(cls, paper_specialization, reviewers_queryset):
        paper_spec = (paper_specialization or "").strip().lower()
        
        if not paper_spec or not reviewers_queryset.exists():
            return []

        reviewers_list = [
            r for r in reviewers_queryset 
            if r.specialization and r.specialization.strip()
        ]
        
        if not reviewers_list:
            return []

        model = cls.get_model()
        paper_embedding = model.encode([paper_spec])
        reviewer_specs = [r.specialization.strip().lower() for r in reviewers_list]
        
        reviewer_embeddings = model.encode(reviewer_specs)
        similarity_scores = cosine_similarity(paper_embedding, reviewer_embeddings).flatten()

        scored_reviewers = []
        for index, score in enumerate(similarity_scores):
            if score >= 0.25:
                scored_reviewers.append({
                    'user_obj': reviewers_list[index],
                    'score': score
                })

        scored_reviewers.sort(key=lambda x: x['score'], reverse=True)

        return [item['user_obj'] for item in scored_reviewers]



class CommitteeService:

    
    @staticmethod
    def get_available_reviewers(user, paper_id):
        # ... (شروط التحقق) ...
        paper = ResearchPaper.objects.get(id=paper_id)
        
        # جلب كل المحكمين
        all_reviewers = User.objects.filter(role='reviewer')
        
        # [كاشف البيانات]: سنطبع تخصصات جميع المحكمين في التيرمينال
        print("--- [DEBUG] قائمة المحكمين وتخصصاتهم ---")
        for r in all_reviewers:
            print(f"Name: {r.full_name} | Specialization: '{r.specialization}'")
        
        ranked_reviewers = AIReviewerMatcherService.rank_reviewers_by_specialization(
            paper_specialization=paper.specialization,
            reviewers_queryset=all_reviewers
        )
        
        return ranked_reviewers
    @staticmethod
    def create_committee(user, paper_id, primary_ids, substitute_ids, blinding_type):
=======
class CommitteeService:

    @staticmethod
    def create_committee(user, paper_id, primary_ids, substitute_ids, blinding_type):

>>>>>>> 8009729a235f7b93b8bdf2dd63e85d842a3aade5
        if getattr(user, 'role', '') != 'editor' and not user.is_staff:
            raise PermissionDenied("غير مصرح لك.")

        try:
            paper = ResearchPaper.objects.get(id=paper_id)
        except ResearchPaper.DoesNotExist:
            raise NotFound("البحث غير موجود.")

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
<<<<<<< HEAD
        users = User.objects.filter(user_id__in=all_ids)
=======

        users = User.objects.filter(user_id__in=all_ids)

>>>>>>> 8009729a235f7b93b8bdf2dd63e85d842a3aade5
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
<<<<<<< HEAD
        return committee

    @staticmethod
    def handle_reviewer_response(user, member_id, is_approved):
=======

        return committee

    # =====================================================

    @staticmethod
    def handle_reviewer_response(user, member_id, is_approved):

>>>>>>> 8009729a235f7b93b8bdf2dd63e85d842a3aade5
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
<<<<<<< HEAD
            committee = Committee.objects.select_for_update().get(id=member.committee_id)
=======

            committee = Committee.objects.select_for_update().get(
                id=member.committee_id
            )
>>>>>>> 8009729a235f7b93b8bdf2dd63e85d842a3aade5

            if committee.status in Committee.FINAL_STATUSES:
                raise ValidationError("القرار النهائي صدر، لا يمكن تغيير الرد.")

            if member.is_approved == is_approved:
                raise ValidationError("الرد نفسه مسجَّل مسبقاً.")

            previously_accepted = member.is_approved is True
<<<<<<< HEAD
=======

>>>>>>> 8009729a235f7b93b8bdf2dd63e85d842a3aade5
            member.is_approved = is_approved

            if is_approved is False:
                member.response = 'declined'
<<<<<<< HEAD
                if previously_accepted:
                    member.paper_decision = 'pending'
                    if committee.status == 'approved':
                        committee.status = 'pending'
                        committee.save()
                    
=======

                if previously_accepted:
                    # إلغاء الصوت السابق إن وجد
                    member.paper_decision = 'pending'
                    # إعادة اللجنة لحالة pending إذا كانت approved
                    if committee.status == 'approved':
                        committee.status = 'pending'
                        committee.save()
                    # إرسال طلب للعضو الاحتياطي الأول المتاح
>>>>>>> 8009729a235f7b93b8bdf2dd63e85d842a3aade5
                    substitute = CommitteeMember.objects.filter(
                        committee=committee,
                        is_substitute=True,
                        is_approved=None
                    ).first()
                    if substitute:
                        send_substitute_invitation_email(substitute)
<<<<<<< HEAD
=======

>>>>>>> 8009729a235f7b93b8bdf2dd63e85d842a3aade5
                member.save()

            elif is_approved is True:
                member.response = 'accepted'
<<<<<<< HEAD
                if member.is_substitute:
                    member.is_substitute = False
                    member.role = 'primary'
                member.save()

=======

                # إذا كان احتياطياً وقبِل → ترقيته لعضو أساسي
                if member.is_substitute:
                    member.is_substitute = False
                    member.role = 'primary'

                member.save()

                # إعادة حساب عدد الموافقين الأساسيين
>>>>>>> 8009729a235f7b93b8bdf2dd63e85d842a3aade5
                approved_count = CommitteeMember.objects.filter(
                    committee=committee,
                    is_substitute=False,
                    is_approved=True
                ).count()

                if approved_count == 3:
                    committee.status = 'approved'
                    committee.save()
<<<<<<< HEAD
        return member

=======

        return member

    # =====================================================

>>>>>>> 8009729a235f7b93b8bdf2dd63e85d842a3aade5
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
<<<<<<< HEAD
=======

>>>>>>> 8009729a235f7b93b8bdf2dd63e85d842a3aade5
        if decision not in VALID:
            raise ValidationError("قرار غير صالح.")

        with transaction.atomic():
<<<<<<< HEAD
=======

>>>>>>> 8009729a235f7b93b8bdf2dd63e85d842a3aade5
            member.paper_decision = decision
            member.comments = comment
            member.save()

            all_members = CommitteeMember.objects.filter(
                committee=member.committee,
                is_substitute=False
            )
<<<<<<< HEAD
            total = all_members.count()
            voted = all_members.filter(paper_decision__in=VALID)
=======

            total = all_members.count()

            voted = all_members.filter(
                paper_decision__in=VALID
            )
>>>>>>> 8009729a235f7b93b8bdf2dd63e85d842a3aade5

            if voted.count() != total:
                return

            accept = voted.filter(paper_decision='accept_paper').count()
            reject = voted.filter(paper_decision='reject_paper').count()
<<<<<<< HEAD
=======

>>>>>>> 8009729a235f7b93b8bdf2dd63e85d842a3aade5
            committee = member.committee

            if accept >= 2:
                committee.status = 'accepted'
            elif reject >= 2:
                committee.status = 'rejected'
            else:
                committee.status = 'revision'
<<<<<<< HEAD
            committee.save()

    @staticmethod
    def get_research_paper_details(user, paper_id):
=======

            committee.save()

    # =====================================================

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
                    send_committee_expiry_email(committee)

    # =====================================================

    @staticmethod
    def get_research_paper_details(user, paper_id):
        from research.models import ResearchPaper
        from rest_framework.exceptions import NotFound

>>>>>>> 8009729a235f7b93b8bdf2dd63e85d842a3aade5
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
<<<<<<< HEAD
        return response_data, is_blinded
=======

        return response_data, is_blinded
    @staticmethod
    def get_available_reviewers(user, paper_id):
        if getattr(user, 'role', '') != 'editor' and not user.is_staff:
            raise PermissionDenied("غير مصرح لك.")

        try:
            paper = ResearchPaper.objects.get(id=paper_id)
        except ResearchPaper.DoesNotExist:
            raise NotFound("البحث غير موجود.")

        available_reviewers = User.objects.filter(
            role='reviewer',
            specialization=paper.specialization
        ).exclude(user_id=paper.author_id)

        return available_reviewers
>>>>>>> 8009729a235f7b93b8bdf2dd63e85d842a3aade5
