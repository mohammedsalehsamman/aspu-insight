from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from committees.models import Committee, CommitteeMember
from committees.utils import send_committee_expiry_email, send_substitute_invitation_email
from research.models import ResearchPaper

User = get_user_model()


def make_user(email, role, **kwargs):
    return User.objects.create(email=email, full_name=email.split('@')[0], role=role, specialization='law', **kwargs)


class SendCommitteeExpiryEmailTests(TestCase):
    def setUp(self):
        self.editor = make_user('editor@example.com', 'editor')
        self.author = make_user('author@example.com', 'author')
        self.paper = ResearchPaper.objects.create(
            title='My Paper', abstract='abstract', author=self.author, specialization='law',
        )
        self.committee = Committee.objects.create(paper=self.paper, editor=self.editor, status='expired')

    @patch('committees.utils.send_mail')
    def test_sends_email_to_editor(self, mock_send_mail):
        send_committee_expiry_email(self.committee)
        mock_send_mail.assert_called_once()
        _, kwargs = mock_send_mail.call_args
        self.assertEqual(kwargs['recipient_list'], [self.editor.email])
        self.assertIn(self.paper.title, kwargs['message'])
        self.assertTrue(kwargs['fail_silently'])


class SendSubstituteInvitationEmailTests(TestCase):
    def setUp(self):
        self.editor = make_user('editor@example.com', 'editor')
        self.author = make_user('author@example.com', 'author')
        self.substitute = make_user('sub@example.com', 'reviewer')
        self.paper = ResearchPaper.objects.create(
            title='My Paper', abstract='abstract', author=self.author, specialization='law',
        )
        self.committee = Committee.objects.create(paper=self.paper, editor=self.editor, status='pending')
        self.member = CommitteeMember.objects.create(
            committee=self.committee, user=self.substitute, role='substitute', is_substitute=True
        )

    @patch('committees.utils.send_mail')
    def test_sends_email_to_substitute_reviewer(self, mock_send_mail):
        send_substitute_invitation_email(self.member)
        mock_send_mail.assert_called_once()
        _, kwargs = mock_send_mail.call_args
        self.assertEqual(kwargs['recipient_list'], [self.substitute.email])
        self.assertIn(self.paper.title, kwargs['message'])
