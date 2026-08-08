from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase

from editorReview.services import EditorReviewService
from research.models import ResearchPaper

User = get_user_model()


class PublishPaperAssignedEditorTests(TestCase):
    def setUp(self):
        self.author = User.objects.create(email="author@example.com", full_name="Author", specialization="law")
        self.assigned_editor = User.objects.create(
            email="assigned@example.com", full_name="Assigned Editor", role="editor", specialization="law",
        )
        self.other_editor = User.objects.create(
            email="other@example.com", full_name="Other Editor", role="editor", specialization="law",
        )
        self.paper = ResearchPaper.objects.create(
            title="Paper", abstract="abstract", author=self.author,
            specialization="law", status=ResearchPaper.Status.ACCEPTED,
            assigned_editor=self.assigned_editor,
        )

    def test_service_rejects_publish_by_editor_not_assigned_to_the_paper(self):
        with self.assertRaises(ValidationError):
            EditorReviewService.publish_paper(self.paper, self.other_editor)


class PublishPaperAPIViewAssignedEditorTests(APITestCase):

    def setUp(self):
        self.author = User.objects.create(
            email="author2@example.com", full_name="Author", specialization="law", email_verified=True,
        )
        self.assigned_editor = User.objects.create(
            email="assigned2@example.com", full_name="Assigned Editor", role="editor", specialization="law",
            email_verified=True,
        )
        self.other_editor = User.objects.create(
            email="other2@example.com", full_name="Other Editor", role="editor", specialization="law",
            email_verified=True,
        )
        self.paper = ResearchPaper.objects.create(
            title="Paper", abstract="abstract", author=self.author,
            specialization="law", status=ResearchPaper.Status.ACCEPTED,
            assigned_editor=self.assigned_editor,
        )
        self.url = reverse('publish-paper', kwargs={'paper_id': self.paper.id})

    def test_editor_not_assigned_to_paper_cannot_publish_it(self):
        self.client.force_authenticate(user=self.other_editor)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.paper.refresh_from_db()
        self.assertNotEqual(
            self.paper.status, ResearchPaper.Status.PUBLISHED,
            "An editor who is not the paper's assigned_editor was able to publish it — "
            "PublishPaperAPIView/EditorReviewService.publish_paper() never calls "
            "_check_assigned_editor(), unlike the initial/final review endpoints."
        )
