from django.contrib.auth import get_user_model
from django.test import TestCase

from research.models import (
    PaperChunkEmbedding,
    PaperDownload,
    PaperEmbedding,
    PlagiarismReport,
    PlagiarismSource,
    ResearchPaper,
)

User = get_user_model()


def make_user(email, role='author', **kwargs):
    return User.objects.create(email=email, full_name=email, role=role, specialization='law', **kwargs)


class StrMethodTests(TestCase):
    def setUp(self):
        self.author = make_user('author@example.com')
        self.paper = ResearchPaper.objects.create(
            title='My Paper', abstract='a', author=self.author, specialization='law',
        )

    def test_research_paper_str_returns_title(self):
        self.assertEqual(str(self.paper), 'My Paper')

    def test_plagiarism_report_str_mentions_paper_title(self):
        report = PlagiarismReport.objects.create(paper=self.paper)
        self.assertIn('My Paper', str(report))

    def test_plagiarism_source_str_returns_source_title(self):
        report = PlagiarismReport.objects.create(paper=self.paper)
        source = PlagiarismSource.objects.create(
            report=report, source_title='Some External Source', match_percentage=42.0,
        )
        self.assertEqual(str(source), 'Some External Source')

    def test_paper_chunk_embedding_str_mentions_chunk_index_and_paper_title(self):
        chunk = PaperChunkEmbedding.objects.create(
            paper=self.paper, chunk_index=3, chunk_text='some text', embedding_vector=[0.1, 0.2],
        )
        self.assertIn('3', str(chunk))
        self.assertIn('My Paper', str(chunk))

    def test_paper_embedding_str_mentions_paper_title(self):
        embedding = PaperEmbedding.objects.create(paper=self.paper, embedding_vector=[0.1, 0.2])
        self.assertIn('My Paper', str(embedding))

    def test_paper_download_str_mentions_paper_title(self):
        download = PaperDownload.objects.create(paper=self.paper, user=self.author)
        self.assertIn('My Paper', str(download))
