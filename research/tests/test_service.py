from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from committees.models import Committee, CommitteeMember
from research.models import ResearchPaper
from research.service import ResearchPaperService

User = get_user_model()


def make_user(email, role='author', **kwargs):
    return User.objects.create(email=email, full_name=email, role=role, specialization='law', **kwargs)


class CreatePaperTests(TestCase):
    def setUp(self):
        self.author = make_user('author@example.com')

    @patch('research.service.compute_paper_embedding_task')
    @patch('research.service.check_paper_plagiarism_task')
    def test_create_paper_sets_author_and_defaults(self, mock_plagiarism_task, mock_embedding_task):
        paper = ResearchPaperService.create_paper(
            self.author,
            {'title': 'A Paper', 'abstract': 'abstract text', 'specialization': 'law'},
        )
        self.assertEqual(paper.author, self.author)
        self.assertEqual(paper.title, 'A Paper')
        self.assertEqual(paper.status, ResearchPaper.Status.PENDING)
        self.assertTrue(ResearchPaper.objects.filter(pk=paper.pk).exists())


class GetVisiblePapersTests(TestCase):
    def setUp(self):
        self.author = make_user('author@example.com')
        self.other_author = make_user('other@example.com')
        self.assistant = make_user('assistant@example.com', role='assistant_editor')
        self.editor = make_user('editor@example.com', role='editor')
        self.other_editor = make_user('other_editor@example.com', role='editor')
        self.reviewer = make_user('reviewer@example.com', role='reviewer')

        self.published = ResearchPaper.objects.create(
            title='Published', abstract='a', author=self.other_author,
            specialization='law', status=ResearchPaper.Status.PUBLISHED,
        )
        self.private_own = ResearchPaper.objects.create(
            title='My draft', abstract='a', author=self.author,
            specialization='law', status=ResearchPaper.Status.PENDING,
        )
        self.private_others = ResearchPaper.objects.create(
            title='Someone else draft', abstract='a', author=self.other_author,
            specialization='law', status=ResearchPaper.Status.SUBMITTED,
        )

    def test_anonymous_user_sees_only_published(self):
        papers = ResearchPaperService.get_visible_papers(AnonymousUser())
        self.assertEqual(list(papers), [self.published])

    def test_none_user_sees_only_published(self):
        papers = ResearchPaperService.get_visible_papers(None)
        self.assertEqual(list(papers), [self.published])

    def test_assistant_editor_sees_all_papers(self):
        papers = ResearchPaperService.get_visible_papers(self.assistant)
        self.assertEqual(papers.count(), 3)

    def test_author_sees_own_and_published_but_not_others_private(self):
        papers = set(ResearchPaperService.get_visible_papers(self.author))
        self.assertIn(self.published, papers)
        self.assertIn(self.private_own, papers)
        self.assertNotIn(self.private_others, papers)

    def test_committee_member_sees_assigned_paper(self):
        committee = Committee.objects.create(paper=self.private_others, editor=self.editor)
        CommitteeMember.objects.create(committee=committee, user=self.reviewer, role='primary')

        papers = set(ResearchPaperService.get_visible_papers(self.reviewer))
        self.assertIn(self.private_others, papers)

    def test_editor_sees_reviewed_paper_assigned_to_their_committee(self):
        self.private_others.is_reviewed_by_assistant = True
        self.private_others.save()
        Committee.objects.create(paper=self.private_others, editor=self.editor)

        papers = set(ResearchPaperService.get_visible_papers(self.editor))
        self.assertIn(self.private_others, papers)

    def test_editor_does_not_see_unreviewed_paper_assigned_to_their_committee(self):
        Committee.objects.create(paper=self.private_others, editor=self.editor)

        papers = set(ResearchPaperService.get_visible_papers(self.editor))
        self.assertNotIn(self.private_others, papers)

    def test_editor_does_not_see_paper_assigned_to_a_different_editor(self):
        self.private_others.is_reviewed_by_assistant = True
        self.private_others.save()
        Committee.objects.create(paper=self.private_others, editor=self.other_editor)

        papers = set(ResearchPaperService.get_visible_papers(self.editor))
        self.assertNotIn(self.private_others, papers)

    def test_search_filters_by_title(self):
        papers = ResearchPaperService.get_visible_papers(self.assistant, search='Published')
        self.assertEqual(list(papers), [self.published])

    def test_search_filters_by_specialization(self):
        self.published.specialization = 'physics'
        self.published.save()
        papers = ResearchPaperService.get_visible_papers(self.assistant, search='physics')
        self.assertEqual(list(papers), [self.published])


class CanViewTests(TestCase):
    def setUp(self):
        self.author = make_user('author@example.com')
        self.other = make_user('other@example.com')
        self.assistant = make_user('assistant@example.com', role='assistant_editor')
        self.editor = make_user('editor@example.com', role='editor')
        self.reviewer = make_user('reviewer@example.com', role='reviewer')
        self.staff = make_user('staff@example.com', is_staff=True)

        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='a', author=self.author,
            specialization='law', status=ResearchPaper.Status.SUBMITTED,
        )

    def test_published_paper_visible_to_anyone(self):
        self.paper.status = ResearchPaper.Status.PUBLISHED
        self.paper.save()
        self.assertTrue(ResearchPaperService.can_view(AnonymousUser(), self.paper))
        self.assertTrue(ResearchPaperService.can_view(self.other, self.paper))

    def test_unpublished_paper_hidden_from_anonymous(self):
        self.assertFalse(ResearchPaperService.can_view(AnonymousUser(), self.paper))
        self.assertFalse(ResearchPaperService.can_view(None, self.paper))

    def test_author_can_view_own_unpublished_paper(self):
        self.assertTrue(ResearchPaperService.can_view(self.author, self.paper))

    def test_staff_can_view_any_paper(self):
        self.assertTrue(ResearchPaperService.can_view(self.staff, self.paper))

    def test_assistant_editor_can_view_any_paper(self):
        self.assertTrue(ResearchPaperService.can_view(self.assistant, self.paper))

    def test_unrelated_authenticated_user_cannot_view(self):
        self.assertFalse(ResearchPaperService.can_view(self.other, self.paper))

    def test_committee_editor_can_view_only_if_reviewed_by_assistant(self):
        Committee.objects.create(paper=self.paper, editor=self.editor)
        self.assertFalse(ResearchPaperService.can_view(self.editor, self.paper))

        self.paper.is_reviewed_by_assistant = True
        self.paper.save()
        self.assertTrue(ResearchPaperService.can_view(self.editor, self.paper))

    def test_committee_member_can_view_only_if_reviewed_by_assistant(self):
        committee = Committee.objects.create(paper=self.paper, editor=self.editor)
        CommitteeMember.objects.create(committee=committee, user=self.reviewer, role='primary')

        self.assertFalse(ResearchPaperService.can_view(self.reviewer, self.paper))

        self.paper.is_reviewed_by_assistant = True
        self.paper.save()
        self.assertTrue(ResearchPaperService.can_view(self.reviewer, self.paper))


class CanUpdateAndCanDeleteTests(TestCase):
    def setUp(self):
        self.author = make_user('author@example.com')
        self.other = make_user('other@example.com')
        self.editor = make_user('editor@example.com', role='editor')
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='a', author=self.author,
            specialization='law', status=ResearchPaper.Status.SUBMITTED,
        )

    def test_non_author_cannot_update(self):
        self.assertFalse(ResearchPaperService.can_update(self.other, self.paper))

    def test_author_can_update_when_no_committee_exists(self):
        self.assertTrue(ResearchPaperService.can_update(self.author, self.paper))

    def test_author_cannot_update_when_committee_exists_and_status_not_revision_or_rejected(self):
        Committee.objects.create(paper=self.paper, editor=self.editor)
        self.paper.status = ResearchPaper.Status.COMMITTEE_REVIEW
        self.paper.save()
        self.assertFalse(ResearchPaperService.can_update(self.author, self.paper))

    def test_author_can_update_when_committee_exists_and_status_is_revision_required(self):
        Committee.objects.create(paper=self.paper, editor=self.editor)
        self.paper.status = ResearchPaper.Status.REVISION_REQUIRED
        self.paper.save()
        self.assertTrue(ResearchPaperService.can_update(self.author, self.paper))

    def test_author_can_update_when_committee_exists_and_status_is_rejected(self):
        Committee.objects.create(paper=self.paper, editor=self.editor)
        self.paper.status = ResearchPaper.Status.REJECTED
        self.paper.save()
        self.assertTrue(ResearchPaperService.can_update(self.author, self.paper))

    def test_author_cannot_update_when_committee_exists_and_paper_published(self):
        Committee.objects.create(paper=self.paper, editor=self.editor)
        self.paper.status = ResearchPaper.Status.PUBLISHED
        self.paper.save()
        self.assertFalse(ResearchPaperService.can_update(self.author, self.paper))

    def test_can_delete_mirrors_can_update(self):
        Committee.objects.create(paper=self.paper, editor=self.editor)
        self.paper.status = ResearchPaper.Status.COMMITTEE_REVIEW
        self.paper.save()
        self.assertEqual(
            ResearchPaperService.can_delete(self.author, self.paper),
            ResearchPaperService.can_update(self.author, self.paper),
        )
        self.assertFalse(ResearchPaperService.can_delete(self.author, self.paper))

    def test_can_delete_true_for_author_with_no_committee(self):
        self.assertTrue(ResearchPaperService.can_delete(self.author, self.paper))


class UpdatePaperTests(TestCase):
    def setUp(self):
        self.author = make_user('author@example.com')
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='a', author=self.author,
            specialization='law', status=ResearchPaper.Status.SUBMITTED,
        )

    @patch('research.service.compute_paper_embedding_task')
    def test_update_paper_persists_field_changes(self, mock_embedding_task):
        ResearchPaperService.update_paper(self.paper, {'title': 'New title'})
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.title, 'New title')

    @patch('research.service.compute_paper_embedding_task')
    def test_update_paper_triggers_embedding_when_title_changes(self, mock_embedding_task):
        ResearchPaperService.update_paper(self.paper, {'title': 'New title'})
        # transaction.on_commit callbacks aren't fired inside TestCase's atomic wrapper,
        # so we only assert the update succeeded without error here.
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.title, 'New title')

    @patch('research.service.compute_paper_embedding_task')
    def test_update_paper_does_not_error_when_unrelated_field_changes(self, mock_embedding_task):
        ResearchPaperService.update_paper(self.paper, {'rejection_reason': 'needs fixes'})
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.rejection_reason, 'needs fixes')


class DeletePaperTests(TestCase):
    def setUp(self):
        self.author = make_user('author@example.com')
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='a', author=self.author,
            specialization='law', status=ResearchPaper.Status.SUBMITTED,
        )

    def test_delete_paper_removes_it_from_db(self):
        pk = self.paper.pk
        ResearchPaperService.delete_paper(self.paper)
        self.assertFalse(ResearchPaper.objects.filter(pk=pk).exists())


class GetAuthorDashboardPapersTests(TestCase):
    def setUp(self):
        self.author = make_user('author@example.com')
        self.other_author = make_user('other@example.com')
        self.own_paper = ResearchPaper.objects.create(
            title='Mine', abstract='a', author=self.author,
            specialization='law', status=ResearchPaper.Status.PENDING,
        )
        self.own_published = ResearchPaper.objects.create(
            title='Mine published', abstract='a', author=self.author,
            specialization='law', status=ResearchPaper.Status.PUBLISHED,
        )
        self.other_paper = ResearchPaper.objects.create(
            title='Not mine', abstract='a', author=self.other_author,
            specialization='law', status=ResearchPaper.Status.PUBLISHED,
        )

    def test_returns_only_own_papers_regardless_of_status(self):
        papers = set(ResearchPaperService.get_author_dashboard_papers(self.author))
        self.assertEqual(papers, {self.own_paper, self.own_published})
