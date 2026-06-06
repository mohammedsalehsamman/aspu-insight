from django.db.models import Q
from django.shortcuts import get_object_or_404

from research.models import ResearchPaper
from committeeMember.models import CommitteeMember



class ResearchPaperService:

    @staticmethod
    def create_paper(user, validated_data):

        return ResearchPaper.objects.create(
            publisher=user,
            **validated_data
        )

    @staticmethod
    def get_paper(pk):

        return get_object_or_404(
            ResearchPaper,
            pk=pk
        )

    @staticmethod
    def get_visible_papers(user):

        committee_papers = CommitteeMember.objects.filter(
            reviewer=user
        ).values_list(
            "committee__paper_id",
            flat=True
        )

        return ResearchPaper.objects.filter(

            Q(
                status=ResearchPaper.Status.PUBLISHED
            )

            |

            Q(
                publisher=user
            )

            |

            Q(
                research_id__in=committee_papers
            )

        ).distinct()

    @staticmethod
    def can_view(user, paper):

        if paper.status == ResearchPaper.Status.PUBLISHED:
            return True

        if paper.publisher == user:
            return True

        return CommitteeMember.objects.filter(
            committee__paper=paper,
            reviewer=user
        ).exists()

    @staticmethod
    def can_update(user, paper):

        if paper.publisher != user:
            return False

        committee_exists = hasattr(
            paper,
            "committee"
        )

        if not committee_exists:
            return True

        return paper.status in [
            ResearchPaper.Status.REVISION_REQUIRED,
            ResearchPaper.Status.REJECTED,
        ]

    @staticmethod
    def can_delete(user, paper):

        return ResearchPaperService.can_update(
            user,
            paper
        )

    @staticmethod
    def update_paper(
        paper,
        validated_data
    ):

        for field, value in validated_data.items():
            setattr(
                paper,
                field,
                value
            )

        paper.save()

        return paper

    @staticmethod
    def delete_paper(paper):

        paper.delete()