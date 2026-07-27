from django.core.management.base import BaseCommand

from research.models import ResearchPaper, PaperEmbedding
from ai_service.tasks import compute_paper_embedding_task


class Command(BaseCommand):
    help = "Queue embedding computation for every existing paper that does not have one yet."

    def add_arguments(self, parser):
        parser.add_argument(
            '--sync', action='store_true',
            help="Run inline instead of dispatching to Celery (useful without a running worker).",
        )

    def handle(self, *args, **options):
        papers = ResearchPaper.objects.exclude(id__in=PaperEmbedding.objects.values_list('paper_id', flat=True))
        count = papers.count()
        self.stdout.write(f"Found {count} paper(s) without a precomputed embedding.")

        for paper in papers:
            if options['sync']:
                compute_paper_embedding_task(paper.id)
            else:
                compute_paper_embedding_task.delay(paper.id)

        mode = "synchronously" if options['sync'] else "via Celery"
        self.stdout.write(self.style.SUCCESS(f"Queued {count} paper(s) for embedding computation ({mode})."))
