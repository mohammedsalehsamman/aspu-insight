from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from research.models import ResearchPaper
from committees.models import Committee, CommitteeMember
from ai_service.tasks import check_paper_plagiarism_task, compute_paper_embedding_task, compute_metadata_quality_task

EMBEDDING_RELEVANT_FIELDS = {'title', 'abstract', 'specialization'}
METADATA_QUALITY_RELEVANT_FIELDS = {'title', 'abstract', 'specialization', 'pdf_file'}

class ResearchPaperService:

    @staticmethod
    def create_paper(user, validated_data):
        paper = ResearchPaper.objects.create(
            author=user,
            **validated_data
        )
        transaction.on_commit(lambda: check_paper_plagiarism_task.delay(paper.id))
        transaction.on_commit(lambda: compute_paper_embedding_task.delay(paper.id))
        return paper

    @staticmethod
    def get_paper(pk):
        return get_object_or_404(
            ResearchPaper.objects.select_related('author'), 
            pk=pk
        )

    @staticmethod
    def _apply_search(queryset, search):
        if not search:
            return queryset
        return queryset.filter(
            Q(title__icontains=search) |
            Q(author__full_name__icontains=search) |
            Q(specialization__icontains=search)
        )

    @staticmethod
    def get_visible_papers(user, search=None):
        if not user or not user.is_authenticated:
            papers = ResearchPaper.objects.filter(status=ResearchPaper.Status.PUBLISHED)
            return ResearchPaperService._apply_search(papers, search)

        is_assistant = getattr(user, 'is_assistant_editor', False) or getattr(user, 'role', '') in ['assistant_editor', 'assistant', 'assistant_editor']

        if is_assistant:
            papers = ResearchPaper.objects.select_related('author').all()
            return ResearchPaperService._apply_search(papers, search)

        assigned_paper_ids = CommitteeMember.objects.filter(
            user=user
        ).values_list('committee__paper_id', flat=True)

        is_editor_role = getattr(user, 'role', '') == 'editor'
        editor_query = Q(committee__editor=user, is_reviewed_by_assistant=True)

        if is_editor_role:
            editor_query = editor_query | Q(is_reviewed_by_assistant=True, committee__isnull=True)

        papers = ResearchPaper.objects.filter(
            Q(status=ResearchPaper.Status.PUBLISHED) |
            Q(author=user) |
            Q(id__in=assigned_paper_ids) |
            editor_query
        ).select_related('author').distinct()

        return ResearchPaperService._apply_search(papers, search)

    @staticmethod
    def get_author_dashboard_papers(user):
        return ResearchPaper.objects.filter(author=user).select_related('author')

    @staticmethod
    def can_view(user, paper):
        if paper.status == ResearchPaper.Status.PUBLISHED:
            return True

        if not user or not user.is_authenticated:
            return False

        is_assistant = getattr(user, 'is_assistant_editor', False) or getattr(user, 'role', '') in ['assistant_editor', 'assistant', 'assistant_editor']

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

        return paper.status in [
            ResearchPaper.Status.REVISION_REQUIRED,
            ResearchPaper.Status.REJECTED,
        ]

    @staticmethod
    def can_delete(user, paper):
        return ResearchPaperService.can_update(user, paper)

    @staticmethod
    def update_paper(paper, validated_data):
        needs_re_embedding = bool(EMBEDDING_RELEVANT_FIELDS & validated_data.keys())
        needs_re_scoring = bool(METADATA_QUALITY_RELEVANT_FIELDS & validated_data.keys())
        for field, value in validated_data.items():
            setattr(paper, field, value)
        paper.save()
        if needs_re_embedding:
            transaction.on_commit(lambda: compute_paper_embedding_task.delay(paper.id))
        if needs_re_scoring:
            transaction.on_commit(lambda: compute_metadata_quality_task.delay(paper.id))
        return paper

    @staticmethod
    def delete_paper(paper):
        paper.delete()