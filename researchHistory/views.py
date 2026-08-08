from rest_framework import generics, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from accounts.permissions import IsAdmin, IsEmailVerified
from researchHistory.models import ResearchHistory
from researchHistory.serializers import ResearchHistorySerializer

class AdminResearchHistoryListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsAdmin, IsEmailVerified]
    serializer_class = ResearchHistorySerializer
    queryset = ResearchHistory.objects.select_related('paper', 'changed_by').order_by('-created_at')
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['paper', 'changed_by', 'to_status']
    ordering_fields = ['created_at']
