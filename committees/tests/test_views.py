from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError, NotFound
from rest_framework.test import APITestCase

from committees.models import Committee, CommitteeMember
from research.models import ResearchPaper

User = get_user_model()


def make_user(email, role, **kwargs):
    return User.objects.create(email=email, full_name=email.split('@')[0], role=role, specialization='law', **kwargs)


class CreateCommitteeViewTests(APITestCase):
    def setUp(self):
        self.editor = make_user('editor@example.com', 'editor')
        self.author = make_user('author@example.com', 'author')
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
        )
        self.url = reverse('create-committee', kwargs={'paper_id': self.paper.id})

    def test_unauthenticated_denied(self):
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch('committees.views.CommitteeService.create_committee')
    def test_editor_creates_committee(self, mock_create):
        mock_create.return_value = None
        self.client.force_authenticate(user=self.editor)
        payload = {
            'primary_users': [1, 2, 3],
            'substitute_users': [4],
            'blinding_type': 'single_blind',
        }
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_create.assert_called_once()

    @patch('committees.views.CommitteeService.create_committee', side_effect=PermissionDenied())
    def test_non_editor_forbidden(self, mock_create):
        self.client.force_authenticate(user=self.author)
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('committees.views.CommitteeService.create_committee', side_effect=ValidationError('bad'))
    def test_validation_error_returns_400(self, mock_create):
        self.client.force_authenticate(user=self.editor)
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ReviewerResponseViewTests(APITestCase):
    def setUp(self):
        self.reviewer = make_user('rev@example.com', 'reviewer')
        self.editor = make_user('editor@example.com', 'editor')
        self.url = reverse('reviewer-respond', kwargs={'member_id': 1})

    def test_unauthenticated_denied(self):
        response = self.client.post(self.url, {'is_approved': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch('committees.views.CommitteeService.handle_reviewer_response')
    def test_reviewer_responds_successfully(self, mock_handle):
        self.client.force_authenticate(user=self.reviewer)
        response = self.client.post(self.url, {'is_approved': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_handle.assert_called_once_with(user=self.reviewer, member_id=1, is_approved=True)

    @patch('committees.views.CommitteeService.handle_reviewer_response', side_effect=PermissionDenied())
    def test_non_reviewer_forbidden(self, mock_handle):
        self.client.force_authenticate(user=self.editor)
        response = self.client.post(self.url, {'is_approved': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('committees.views.CommitteeService.handle_reviewer_response', side_effect=NotFound())
    def test_member_not_found(self, mock_handle):
        self.client.force_authenticate(user=self.reviewer)
        response = self.client.post(self.url, {'is_approved': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class SubmitReviewDecisionViewTests(APITestCase):
    def setUp(self):
        self.reviewer = make_user('rev@example.com', 'reviewer')
        self.url = reverse('submit-decision', kwargs={'member_id': 1})

    def test_unauthenticated_denied(self):
        response = self.client.post(self.url, {'decision': 'accept_paper'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch('committees.views.CommitteeService.submit_review_decision')
    def test_reviewer_submits_decision(self, mock_submit):
        self.client.force_authenticate(user=self.reviewer)
        response = self.client.post(self.url, {'decision': 'accept_paper', 'comment': 'ok'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_submit.assert_called_once_with(user=self.reviewer, member_id=1, decision='accept_paper', comment='ok')

    @patch('committees.views.CommitteeService.submit_review_decision', side_effect=ValidationError('bad'))
    def test_invalid_decision_returns_400(self, mock_submit):
        self.client.force_authenticate(user=self.reviewer)
        response = self.client.post(self.url, {'decision': 'bogus'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class GetAvailableReviewersViewTests(APITestCase):
    def setUp(self):
        self.editor = make_user('editor@example.com', 'editor')
        self.author = make_user('author@example.com', 'author')
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
        )
        self.url = reverse('available-reviewers', kwargs={'paper_id': self.paper.id})

    def test_unauthenticated_denied(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch('committees.views.CommitteeService.get_available_reviewers')
    def test_editor_gets_list(self, mock_get):
        reviewer = make_user('rev@example.com', 'reviewer')
        mock_get.return_value = [reviewer]
        self.client.force_authenticate(user=self.editor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['email'], 'rev@example.com')

    @patch('committees.views.CommitteeService.get_available_reviewers', side_effect=PermissionDenied())
    def test_non_editor_forbidden(self, mock_get):
        self.client.force_authenticate(user=self.author)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class FetchResearchPaperDetailsViewTests(APITestCase):
    def setUp(self):
        self.author = make_user('author@example.com', 'author')
        self.reviewer = make_user('rev@example.com', 'reviewer')
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
        )
        self.url = reverse('paper-details', kwargs={'paper_id': self.paper.id})

    def test_unauthenticated_denied(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_gets_paper_details(self):
        self.client.force_authenticate(user=self.reviewer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.paper.id)

    def test_missing_paper_returns_404(self):
        self.client.force_authenticate(user=self.reviewer)
        url = reverse('paper-details', kwargs={'paper_id': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class CommitteeDetailViewTests(APITestCase):
    def setUp(self):
        self.editor = make_user('editor@example.com', 'editor')
        self.author = make_user('author@example.com', 'author')
        self.reviewer = make_user('rev@example.com', 'reviewer')
        self.outsider = make_user('outsider@example.com', 'reviewer')
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
        )
        self.committee = Committee.objects.create(paper=self.paper, editor=self.editor, status='pending')
        CommitteeMember.objects.create(committee=self.committee, user=self.reviewer, role='primary')
        self.url = reverse('committee-detail', kwargs={'paper_id': self.paper.id})

    def test_unauthenticated_denied(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_no_committee_returns_404(self):
        other_author = make_user('other@example.com', 'author')
        other_paper = ResearchPaper.objects.create(
            title='Other', abstract='abstract', author=other_author, specialization='law',
        )
        self.client.force_authenticate(user=self.editor)
        url = reverse('committee-detail', kwargs={'paper_id': other_paper.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_editor_owner_can_view(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_committee_member_can_view(self):
        self.client.force_authenticate(user=self.reviewer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_staff_can_view(self):
        staff = make_user('staff@example.com', 'author', is_staff=True)
        self.client.force_authenticate(user=staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_outsider_forbidden(self):
        self.client.force_authenticate(user=self.outsider)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_author_can_view(self):
        self.client.force_authenticate(user=self.author)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_author_view_hides_reviewer_identity_when_blinded(self):
        self.client.force_authenticate(user=self.author)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        member = response.data['members'][0]
        self.assertEqual(member['user']['full_name'], 'محكم مخفي')

    def test_author_view_exposes_requested_revisions(self):
        self.committee.status = 'revision'
        self.committee.save()
        CommitteeMember.objects.filter(committee=self.committee, user=self.reviewer).update(
            paper_decision='modify_paper', comments='يرجى توضيح المنهجية.'
        )
        self.client.force_authenticate(user=self.author)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('يرجى توضيح المنهجية.', response.data['requested_revisions'])
