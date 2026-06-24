from django.db.models import Q
from django.shortcuts import get_object_or_404
from research.models import ResearchPaper
from committees.models import Committee, CommitteeMember

class ResearchPaperService:

    @staticmethod
    def create_paper(user, validated_data):
        return ResearchPaper.objects.create(
            author=user,
            **validated_data
        )

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

        assigned_paper_ids = CommitteeMember.objects.filter(
            user=user
        ).values_list('committee__paper_id', flat=True)

        return ResearchPaper.objects.filter(
            Q(status='approved') |
            Q(author=user) |
            Q(id__in=assigned_paper_ids) |
            Q(committee__editor=user)
        ).select_related('author').distinct()

    @staticmethod
    def can_view(user, paper):
        if paper.status == 'approved':
            return True

        if not user or not user.is_authenticated:
            return False

        if paper.author == user or user.is_staff: 
            return True

        if Committee.objects.filter(paper=paper, editor=user).exists():
            return True

        return CommitteeMember.objects.filter(
            committee__paper=paper,
            user=user
        ).exists()

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