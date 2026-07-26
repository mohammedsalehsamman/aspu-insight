from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, NotFound
from .services import CommitteeService
from .serializers import CommitteeMemberUserSerializer, CommitteeDetailsSerializer
from .models import Committee

class CreateCommitteeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, paper_id):
        primary_ids = request.data.get('primary_users', [])
        substitute_ids = request.data.get('substitute_users', [])
        blinding_type = request.data.get('blinding_type', 'single_blind')

        CommitteeService.create_committee(
            user=request.user,
            paper_id=paper_id,
            primary_ids=primary_ids,
            substitute_ids=substitute_ids,
            blinding_type=blinding_type
        )
        return Response({"detail": "تم إنشاء اللجنة وإرسال الطلبات بنجاح."}, status=status.HTTP_201_CREATED)

class ReviewerResponseAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, member_id):
        is_approved = request.data.get('is_approved')
        
        CommitteeService.handle_reviewer_response(
            user=request.user,
            member_id=member_id,
            is_approved=is_approved
        )
        return Response({"detail": "تم تسجيل ردك بنجاح وتحديث حالة اللجنة."}, status=status.HTTP_200_OK)

class SubmitReviewDecisionAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, member_id):
        decision = request.data.get('decision')
        comment = request.data.get('comment', '')

        CommitteeService.submit_review_decision(
            user=request.user,
            member_id=member_id,
            decision=decision,
            comment=comment
        )
        return Response({"detail": "تم إرسال قرارك العلمي وحفظه بنجاح."}, status=status.HTTP_200_OK)

class FetchResearchPaperDetailsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, paper_id):
        response_data, is_blinded = CommitteeService.get_research_paper_details(
            user=request.user,
            paper_id=paper_id
        )
        return Response(response_data, status=status.HTTP_200_OK)

class GetAvailableReviewersAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, paper_id):
        reviewers = CommitteeService.get_available_reviewers(
            user=request.user,
            paper_id=paper_id
        )
        serializer = CommitteeMemberUserSerializer(reviewers, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class CommitteeDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, paper_id):
        user = request.user
        try:
            committee = Committee.objects.select_related('editor', 'paper', 'paper__author').get(paper_id=paper_id)
        except Committee.DoesNotExist:
            raise NotFound("لا توجد لجنة تحكيم لهذا البحث.")

        is_member = committee.committee_assigned_members.filter(user=user).exists()
        if not (user.is_staff or committee.editor_id == getattr(user, 'user_id', None) or is_member):
            raise PermissionDenied("غير مصرح لك بعرض تفاصيل هذه اللجنة.")

        serializer = CommitteeDetailsSerializer(committee, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)