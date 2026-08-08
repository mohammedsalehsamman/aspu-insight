from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from research.models import ResearchPaper
from researchHistory.models import ResearchHistory

User = get_user_model()


def make_user(email, role='author', **kwargs):
    kwargs.setdefault('email_verified', True)
    return User.objects.create(email=email, full_name=email, role=role, specialization='law', **kwargs)


class AdminResearchHistoryListViewTests(APITestCase):
    def setUp(self):
        self.url = reverse('admin-research-history-list')
        self.admin = make_user('admin@example.com', role='admin')
        self.editor = make_user('editor@example.com', role='editor')
        self.author = make_user('author@example.com')

        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='a', author=self.author, specialization='law',
        )
        self.entry_one = ResearchHistory.objects.create(
            paper=self.paper, from_status='pending', to_status='submitted',
            changed_by=self.editor, note='first',
        )
        self.entry_two = ResearchHistory.objects.create(
            paper=self.paper, from_status='submitted', to_status='editor_review',
            changed_by=self.editor, note='second',
        )

    def test_unauthenticated_denied(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_admin_denied(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_list_history(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 2)

    def test_admin_results_ordered_by_created_at_descending(self):
        # auto_now_add can produce identical timestamps for entries created
        # back-to-back within the same test; use .update() (which bypasses
        # auto_now_add, unlike .save()) to force a deterministic order.
        now = timezone.now()
        ResearchHistory.objects.filter(pk=self.entry_one.pk).update(created_at=now - timedelta(minutes=5))
        ResearchHistory.objects.filter(pk=self.entry_two.pk).update(created_at=now)

        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)
        results = response.data.get('results', response.data)
        self.assertEqual(results[0]['note'], 'second')
        self.assertEqual(results[1]['note'], 'first')

    def test_filter_by_paper(self):
        other_author = make_user('other@example.com')
        other_paper = ResearchPaper.objects.create(
            title='Other', abstract='a', author=other_author, specialization='law',
        )
        ResearchHistory.objects.create(
            paper=other_paper, from_status='pending', to_status='submitted', note='unrelated',
        )

        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url, {'paper': self.paper.id})
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r['paper'] == self.paper.id for r in results))

    def test_filter_by_to_status(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url, {'to_status': 'editor_review'})
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['note'], 'second')

    def test_filter_by_changed_by(self):
        other_editor = make_user('editor2@example.com', role='editor')
        ResearchHistory.objects.create(
            paper=self.paper, from_status='editor_review', to_status='committee_review',
            changed_by=other_editor, note='third',
        )

        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url, {'changed_by': other_editor.user_id})
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['note'], 'third')

    def test_response_is_read_only_representation(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)
        results = response.data.get('results', response.data)
        entry = results[0]
        self.assertIn('from_status', entry)
        self.assertIn('to_status', entry)
        self.assertIn('changed_by', entry)
        self.assertIn('created_at', entry)
