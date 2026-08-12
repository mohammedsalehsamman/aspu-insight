from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory

from committees.models import Committee, CommitteeMember
from committees.serializers import CommitteeDetailsSerializer, CommitteeInvitationSerializer
from research.models import ResearchPaper

User = get_user_model()


def make_user(email, role, **kwargs):
    return User.objects.create(email=email, full_name=email.split('@')[0], role=role, specialization='law', **kwargs)


class CommitteeDetailsSerializerTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.author = make_user('author@example.com', 'author')
        self.editor = make_user('editor@example.com', 'editor')
        self.reviewers = [make_user(f'rev{i}@example.com', 'reviewer') for i in range(3)]
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
        )
        self.committee = Committee.objects.create(
            paper=self.paper, editor=self.editor, status='pending', blinding_type='double_blind'
        )
        self.members = [
            CommitteeMember.objects.create(committee=self.committee, user=r, role='primary', is_substitute=False)
            for r in self.reviewers
        ]

    def _serialize(self, requesting_user):
        request = self.factory.get('/')
        request.user = requesting_user
        return CommitteeDetailsSerializer(self.committee, context={'request': request}).data

    def test_author_sees_hidden_members_when_blinded(self):
        data = self._serialize(self.author)
        for m in data['members']:
            self.assertEqual(m['user']['full_name'], 'محكم مخفي')

    def test_non_author_sees_real_member_data(self):
        data = self._serialize(self.editor)
        names = {m['user']['full_name'] for m in data['members']}
        self.assertEqual(names, {r.full_name for r in self.reviewers})

    def test_open_blinding_shows_members_to_author(self):
        self.committee.blinding_type = 'open'
        self.committee.save()
        data = self._serialize(self.author)
        names = {m['user']['full_name'] for m in data['members']}
        self.assertEqual(names, {r.full_name for r in self.reviewers})

    def test_committee_member_sees_hidden_author_name_when_double_blind(self):
        data = self._serialize(self.reviewers[0])
        self.assertEqual(data['paper_author_name'], 'باحث مخفي')

    def test_non_member_sees_real_author_name(self):
        data = self._serialize(self.editor)
        self.assertEqual(data['paper_author_name'], self.author.full_name)

    def test_single_blind_does_not_hide_author_name_from_member(self):
        self.committee.blinding_type = 'single_blind'
        self.committee.save()
        data = self._serialize(self.reviewers[0])
        self.assertEqual(data['paper_author_name'], self.author.full_name)

    def test_requested_revisions_empty_when_not_in_revision_status(self):
        data = self._serialize(self.editor)
        self.assertEqual(data['requested_revisions'], [])

    def test_requested_revisions_lists_modify_comments(self):
        self.committee.status = 'revision'
        self.committee.save()
        self.members[0].paper_decision = 'modify_paper'
        self.members[0].comments = 'fix references'
        self.members[0].save()
        self.members[1].paper_decision = 'modify_paper'
        self.members[1].comments = ''
        self.members[1].save()

        data = self._serialize(self.editor)
        self.assertEqual(data['requested_revisions'], ['fix references'])

    def test_editor_name_and_paper_title_included(self):
        data = self._serialize(self.editor)
        self.assertEqual(data['editor_name'], self.editor.full_name)
        self.assertEqual(data['paper_title'], self.paper.title)


class CommitteeInvitationSerializerTests(TestCase):
    def setUp(self):
        self.author = make_user('author@example.com', 'author')
        self.editor = make_user('editor@example.com', 'editor')
        self.reviewers = [make_user(f'rev{i}@example.com', 'reviewer') for i in range(3)]
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
        )
        self.committee = Committee.objects.create(paper=self.paper, editor=self.editor, status='pending')
        self.members = [
            CommitteeMember.objects.create(committee=self.committee, user=r, role='primary', is_substitute=False)
            for r in self.reviewers
        ]

    def test_committee_member_ids_excludes_self_and_includes_peers(self):
        data = CommitteeInvitationSerializer(self.members[0]).data
        self.assertNotIn(self.members[0].id, data['committee_member_ids'])
        self.assertEqual(set(data['committee_member_ids']), {self.members[1].id, self.members[2].id})

    def test_committee_member_ids_excludes_substitutes(self):
        substitute_reviewer = make_user('sub@example.com', 'reviewer')
        substitute = CommitteeMember.objects.create(
            committee=self.committee, user=substitute_reviewer, role='substitute', is_substitute=True
        )
        data = CommitteeInvitationSerializer(self.members[0]).data
        self.assertNotIn(substitute.id, data['committee_member_ids'])

    def test_committee_member_ids_empty_when_sole_member(self):
        solo_paper = ResearchPaper.objects.create(
            title='Solo Paper', abstract='abstract', author=self.author, specialization='law',
        )
        solo_committee = Committee.objects.create(paper=solo_paper, editor=self.editor, status='pending')
        solo_member = CommitteeMember.objects.create(committee=solo_committee, user=self.reviewers[0], role='primary')
        data = CommitteeInvitationSerializer(solo_member).data
        self.assertEqual(data['committee_member_ids'], [])
