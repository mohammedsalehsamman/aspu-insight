from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from research.models import ResearchPaper
from editorReview.models import EditorReview
from assistantReview.models import AssistantReview
from committees.models import Committee
from ai_service.models import IEEECheckReport, ClaimEvidenceGraphReport


class DashboardBaseTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create(
            email="admin@example.com", full_name="Admin", role="admin", specialization="law",
            email_verified=True,
        )
        self.editor = User.objects.create(
            email="editor@example.com", full_name="Editor", role="editor", specialization="law",
            email_verified=True,
        )
        self.author = User.objects.create(
            email="author@example.com", full_name="Author", role="author", specialization="law",
            email_verified=True,
        )


class AdminDashboardStatsViewTest(DashboardBaseTest):
    def setUp(self):
        super().setUp()
        self.url = reverse('admin-dashboard-stats')

        # extra users for role/status breakdown
        self.assistant = User.objects.create(
            email="assistant@example.com", full_name="Assistant", role="assistant_editor",
            specialization="law", email_verified=True,
        )
        self.reviewer = User.objects.create(
            email="reviewer@example.com", full_name="Reviewer", role="reviewer",
            specialization="law", is_active=False, email_verified=False,
        )

        self.paper1 = ResearchPaper.objects.create(
            title="P1", abstract="a1", author=self.author, specialization="law",
            status=ResearchPaper.Status.SUBMITTED,
        )
        self.paper2 = ResearchPaper.objects.create(
            title="P2", abstract="a2", author=self.author, specialization="law",
            status=ResearchPaper.Status.PUBLISHED,
        )
        self.paper3 = ResearchPaper.objects.create(
            title="P3", abstract="a3", author=self.author, specialization="law",
            status=ResearchPaper.Status.PUBLISHED,
        )

        EditorReview.objects.create(
            paper=self.paper1, editor=self.editor, notes="n",
            decision=EditorReview.Decision.ACCEPT,
        )
        EditorReview.objects.create(
            paper=self.paper2, editor=self.editor, notes="n",
            decision=EditorReview.Decision.REJECT,
        )
        AssistantReview.objects.create(
            paper=self.paper1, assistant=self.assistant, notes="n",
            decision=AssistantReview.Decision.APPROVE,
        )

        Committee.objects.create(
            paper=self.paper1, editor=self.editor, status='pending',
            deadline=timezone.now() - timedelta(days=1),  # overdue, non-final status
        )
        Committee.objects.create(
            paper=self.paper2, editor=self.editor, status='accepted',
            deadline=timezone.now() - timedelta(days=1),  # overdue but final -> excluded
        )

        IEEECheckReport.objects.create(status=IEEECheckReport.Status.PASS)
        IEEECheckReport.objects.create(status=IEEECheckReport.Status.PASS)
        IEEECheckReport.objects.create(status=IEEECheckReport.Status.FAIL)

        ClaimEvidenceGraphReport.objects.create(status=ClaimEvidenceGraphReport.Status.COMPLETED)

    def test_requires_authentication(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_forbidden_for_non_admin(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_forbidden_for_author(self):
        self.client.force_authenticate(user=self.author)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_stats_counts_correct(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # 6 users total: admin, editor, author, assistant, reviewer (+ any created in setUp)
        self.assertEqual(data['users']['total'], User.objects.count())
        self.assertEqual(data['users']['by_role'].get('admin'), 1)
        self.assertEqual(data['users']['by_role'].get('editor'), 1)
        self.assertEqual(data['users']['by_role'].get('reviewer'), 1)
        self.assertEqual(data['users']['inactive'], 1)
        self.assertEqual(data['users']['unverified_email'], User.objects.filter(email_verified=False).count())

        self.assertEqual(data['papers']['total'], 3)
        self.assertEqual(data['papers']['by_status'].get('submitted'), 1)
        self.assertEqual(data['papers']['by_status'].get('published'), 2)

        self.assertEqual(data['reviews']['editor_reviews_by_decision'].get('ACCEPT'), 1)
        self.assertEqual(data['reviews']['editor_reviews_by_decision'].get('REJECT'), 1)
        self.assertEqual(data['reviews']['assistant_reviews_by_decision'].get('APPROVE'), 1)

        self.assertEqual(data['committees']['by_status'].get('pending'), 1)
        self.assertEqual(data['committees']['by_status'].get('accepted'), 1)
        self.assertEqual(data['committees']['overdue'], 1)

        self.assertEqual(data['ai_reports']['ieee_checks_by_status'].get('pass'), 2)
        self.assertEqual(data['ai_reports']['ieee_checks_by_status'].get('fail'), 1)
        self.assertEqual(data['ai_reports']['claim_evidence_by_status'].get('completed'), 1)

    def test_stats_with_empty_database_returns_zero_counts(self):
        # remove all fixture rows created in setUp
        Committee.objects.all().delete()
        AssistantReview.objects.all().delete()
        EditorReview.objects.all().delete()
        ResearchPaper.objects.all().delete()
        IEEECheckReport.objects.all().delete()
        ClaimEvidenceGraphReport.objects.all().delete()
        User.objects.all().delete()

        self.admin = User.objects.create(
            email="onlyadmin@example.com", full_name="Only Admin", role="admin", specialization="law",
            email_verified=True,
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['papers']['total'], 0)
        self.assertEqual(response.data['papers']['by_status'], {})
        self.assertEqual(response.data['committees']['overdue'], 0)


class AdminPaperListViewTest(DashboardBaseTest):
    def setUp(self):
        super().setUp()
        self.url = reverse('admin-dashboard-papers')
        self.paper1 = ResearchPaper.objects.create(
            title="Alpha Paper", abstract="a", author=self.author, specialization="law",
            status=ResearchPaper.Status.SUBMITTED,
        )
        self.paper2 = ResearchPaper.objects.create(
            title="Beta Paper", abstract="b", author=self.author, specialization="medicine",
            status=ResearchPaper.Status.PUBLISHED,
        )

    def test_requires_authentication(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_forbidden_for_non_admin(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_list_papers(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 2)

    def test_filter_by_status(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url, {'status': 'submitted'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], "Alpha Paper")

    def test_search_by_title(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url, {'search': 'Beta'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], "Beta Paper")


class AdminPaperDetailViewTest(DashboardBaseTest):
    def setUp(self):
        super().setUp()
        self.paper = ResearchPaper.objects.create(
            title="Detail Paper", abstract="a", author=self.author, specialization="law",
        )
        self.url = reverse('admin-dashboard-paper-detail', kwargs={'pk': self.paper.pk})

    def test_forbidden_for_non_admin(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_retrieve_paper_with_history(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], "Detail Paper")
        self.assertIn('history', response.data)

    def test_404_for_missing_paper(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse('admin-dashboard-paper-detail', kwargs={'pk': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class AdminAssignEditorViewTest(DashboardBaseTest):
    def setUp(self):
        super().setUp()
        self.other_editor = User.objects.create(
            email="editor2@example.com", full_name="Editor2", role="editor", specialization="law",
        )
        self.paper = ResearchPaper.objects.create(
            title="Assign Paper", abstract="a", author=self.author, specialization="law",
        )
        self.url = reverse('admin-dashboard-assign-editor', kwargs={'pk': self.paper.pk})

    def test_forbidden_for_non_admin(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.patch(self.url, {'editor_id': self.editor.user_id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_assign_editor(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(self.url, {'editor_id': self.other_editor.user_id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.assigned_editor, self.other_editor)

    def test_admin_can_unassign_editor_with_null(self):
        self.paper.assigned_editor = self.other_editor
        self.paper.save(update_fields=['assigned_editor'])

        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(self.url, {'editor_id': None}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.paper.refresh_from_db()
        self.assertIsNone(self.paper.assigned_editor)

    def test_404_when_paper_missing(self):
        url = reverse('admin-dashboard-assign-editor', kwargs={'pk': 99999})
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(url, {'editor_id': self.other_editor.user_id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_400_when_target_user_is_not_editor(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(self.url, {'editor_id': self.author.user_id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_400_when_editor_id_missing_from_body(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class AdminEditorReviewListViewTest(DashboardBaseTest):
    def setUp(self):
        super().setUp()
        self.url = reverse('admin-dashboard-editor-reviews')
        self.paper = ResearchPaper.objects.create(
            title="P", abstract="a", author=self.author, specialization="law",
        )
        EditorReview.objects.create(
            paper=self.paper, editor=self.editor, notes="n",
            decision=EditorReview.Decision.ACCEPT,
        )

    def test_forbidden_for_non_admin(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_list_editor_reviews(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['decision'], EditorReview.Decision.ACCEPT)


class AdminAssistantReviewListViewTest(DashboardBaseTest):
    def setUp(self):
        super().setUp()
        self.assistant = User.objects.create(
            email="assistant@example.com", full_name="Assistant", role="assistant_editor",
            specialization="law", email_verified=True,
        )
        self.url = reverse('admin-dashboard-assistant-reviews')
        self.paper = ResearchPaper.objects.create(
            title="P", abstract="a", author=self.author, specialization="law",
        )
        AssistantReview.objects.create(
            paper=self.paper, assistant=self.assistant, notes="n",
            decision=AssistantReview.Decision.REJECT,
        )

    def test_forbidden_for_non_admin(self):
        self.client.force_authenticate(user=self.assistant)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_list_assistant_reviews(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['decision'], AssistantReview.Decision.REJECT)


class AdminCommitteeListViewTest(DashboardBaseTest):
    def setUp(self):
        super().setUp()
        self.url = reverse('admin-dashboard-committees')
        self.paper = ResearchPaper.objects.create(
            title="P", abstract="a", author=self.author, specialization="law",
        )
        Committee.objects.create(paper=self.paper, editor=self.editor, status='pending')

    def test_forbidden_for_non_admin(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_list_committees(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['status'], 'pending')
