from django.db.models import Q
from django.shortcuts import get_object_or_404
from research.models import ResearchPaper
from committees.models import Committee, CommitteeMember
from ai_service.tasks import check_paper_plagiarism_task

class ResearchPaperService:

    @staticmethod
    def create_paper(user, validated_data):
        paper = ResearchPaper.objects.create(
            author=user,
            **validated_data
        )
        check_paper_plagiarism_task.delay(paper.id)
        return paper

    @staticmethod
    def get_paper(pk):
        return get_object_or_404(
            ResearchPaper.objects.select_related('author'), 
            pk=pk
        )

    @staticmethod
    def get_visible_papers(user):
        if not user or not user.is_authenticated:
            return ResearchPaper.objects.filter(status='approved')

        is_assistant = getattr(user, 'is_assistant_editor', False) or getattr(user, 'role', '') in ['assistant_editor', 'assistant', 'reviewer_assistant']

        if is_assistant:
            return ResearchPaper.objects.select_related('author').all()

        assigned_paper_ids = CommitteeMember.objects.filter(
            user=user
        ).values_list('committee__paper_id', flat=True)

        is_editor_role = getattr(user, 'role', '') == 'editor'
        editor_query = Q(committee__editor=user, is_reviewed_by_assistant=True)
        
        # الاعتماد على الفحص العكسي الذكي: إذا لم تكن هناك لجنة بعد (أي قيد الانتظار للتعيين)
        if is_editor_role:
            editor_query = editor_query | Q(is_reviewed_by_assistant=True, committee__isnull=True)

        return ResearchPaper.objects.filter(
            Q(status='approved') |
            Q(author=user) |
            Q(id__in=assigned_paper_ids) |
            editor_query
        ).select_related('author').distinct()

    @staticmethod
    def get_author_dashboard_papers(user):
        return ResearchPaper.objects.filter(author=user).select_related('author')

    @staticmethod
    def can_view(user, paper):
        if paper.status == 'approved':
            return True

        if not user or not user.is_authenticated:
            return False

        is_assistant = getattr(user, 'is_assistant_editor', False) or getattr(user, 'role', '') in ['assistant_editor', 'assistant', 'reviewer_assistant']

        if is_assistant:
            return True

        if paper.author == user or user.is_staff: 
            return True

        if Committee.objects.filter(paper=paper, editor=user).exists():
            return paper.is_reviewed_by_assistant

        return CommitteeMember.objects.filter(
            committee__paper=paper,
            user=user
        ).exists() and paper.is_reviewed_by_assistant

    @staticmethod
    def can_update(user, paper):
        if paper.author != user:
            return False

        committee_exists = Committee.objects.filter(paper=paper).exists()

        if not committee_exists:
            return True

        return paper.status in ['under_review', 'rejected']

    @staticmethod
    def can_delete(user, paper):
        return ResearchPaperService.can_update(user, paper)

    @staticmethod
    def update_paper(paper, validated_data):
        for field, value in validated_data.items():
            setattr(paper, field, value)
        paper.save()
        return paper

    @staticmethod
    def delete_paper(paper):
        paper.delete()

    @staticmethod
    def submit_assistant_report(paper, report_text):
        paper.assistant_editor_report = report_text
        paper.is_reviewed_by_assistant = True
        paper.save()
        return paper