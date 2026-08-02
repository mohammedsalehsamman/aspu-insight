from django.db.models import Avg, Count, Q
from django.utils import timezone
from datetime import timedelta

from rest_framework import generics, filters, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from accounts.permissions import IsAdmin
from accounts.models import User
from research.models import ResearchPaper, MetadataQualityReport
from editorReview.models import EditorReview
from editorReview.serializers import EditorReviewSerializer
from assistantReview.models import AssistantReview
from assistantReview.serializers import AssistantReviewSerializer
from committees.models import Committee
from committees.serializers import CommitteeDetailsSerializer
from ai_service.models import IEEECheckReport, ClaimEvidenceGraphReport
from notifications.models import Notification
from notifications.services import NotificationService

from dashboard.serializers import (
    AdminResearchPaperSerializer,
    AdminResearchPaperDetailSerializer,
    AssignEditorSerializer,
)

def _counts_by(queryset, field):
    return {row[field]: row['count'] for row in queryset.values(field).annotate(count=Count(field))}

class AdminDashboardStatsView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        last_30_days = timezone.now() - timedelta(days=30)

        users_qs = User.objects.all()
        papers_qs = ResearchPaper.objects.all()

        data = {
            "users": {
                "total": users_qs.count(),
                "by_role": _counts_by(users_qs, 'role'),
                "inactive": users_qs.filter(is_active=False).count(),
                "unverified_email": users_qs.filter(email_verified=False).count(),
                "new_last_30_days": users_qs.filter(created_at__gte=last_30_days).count(),
            },
            "papers": {
                "total": papers_qs.count(),
                "by_status": _counts_by(papers_qs, 'status'),
                "submitted_last_30_days": papers_qs.filter(created_at__gte=last_30_days).count(),
            },
            "reviews": {
                "editor_reviews_by_decision": _counts_by(EditorReview.objects.all(), 'decision'),
                "assistant_reviews_by_decision": _counts_by(AssistantReview.objects.all(), 'decision'),
            },
            "committees": {
                "by_status": _counts_by(Committee.objects.all(), 'status'),
                "overdue": Committee.objects.filter(
                    deadline__lt=timezone.now()
                ).exclude(status__in=Committee.FINAL_STATUSES).count(),
            },
            "ai_reports": {
                "ieee_checks_by_status": _counts_by(IEEECheckReport.objects.all(), 'status'),
                "claim_evidence_by_status": _counts_by(ClaimEvidenceGraphReport.objects.all(), 'status'),
                "metadata_quality": {
                    "by_status": _counts_by(MetadataQualityReport.objects.all(), 'status'),
                    "average_score": MetadataQualityReport.objects.filter(
                        status=MetadataQualityReport.Status.COMPLETED
                    ).aggregate(avg=Avg('overall_score'))['avg'],
                },
            },
        }
        return Response(data)

class AdminPaperListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = AdminResearchPaperSerializer
    queryset = ResearchPaper.objects.select_related('author', 'assigned_editor').order_by('-created_at')
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'specialization', 'is_paid_open_access']
    search_fields = ['title', 'author__full_name', 'author__email']
    ordering_fields = ['created_at', 'updated_at', 'status']

class AdminPaperDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = AdminResearchPaperDetailSerializer
    queryset = ResearchPaper.objects.select_related('author', 'assigned_editor')

class AdminAssignEditorView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def patch(self, request, pk):
        try:
            paper = ResearchPaper.objects.get(pk=pk)
        except ResearchPaper.DoesNotExist:
            return Response({'error': 'البحث غير موجود.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = AssignEditorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        editor_id = serializer.validated_data['editor_id']

        if editor_id is None:
            paper.assigned_editor = None
        else:
            try:
                editor = User.objects.get(user_id=editor_id, role='editor')
            except User.DoesNotExist:
                return Response({'error': 'المستخدم المطلوب غير موجود أو ليس محرراً.'}, status=status.HTTP_400_BAD_REQUEST)
            paper.assigned_editor = editor

        paper.save(update_fields=['assigned_editor'])

        if editor_id is not None:
            NotificationService.create_notification(
                recipient=editor,
                notification_type=Notification.NotificationType.EDITOR_ASSIGNED,
                actor=request.user,
                target=paper,
                target_repr=paper.title,
                context={
                    'paper_title': paper.title,
                    'fallback_title': 'تم تعيينك محرراً لبحث',
                    'fallback_body': f"تم تعيينك محرراً مسؤولاً عن البحث: {paper.title}",
                },
            )

        return Response(AdminResearchPaperSerializer(paper).data)

class AdminEditorReviewListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = EditorReviewSerializer
    queryset = EditorReview.objects.select_related('editor', 'paper').order_by('-reviewed_at')
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['stage', 'decision', 'editor']
    ordering_fields = ['reviewed_at']

class AdminAssistantReviewListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = AssistantReviewSerializer
    queryset = AssistantReview.objects.select_related('assistant', 'paper').order_by('-reviewed_at')
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['decision', 'assistant']
    ordering_fields = ['reviewed_at']

class AdminCommitteeListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = CommitteeDetailsSerializer
    queryset = Committee.objects.select_related('editor', 'paper', 'paper__author').order_by('-created_at')
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'blinding_type']
    ordering_fields = ['created_at']
