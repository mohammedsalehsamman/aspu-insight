from django.urls import path
from .views import (
    CreateCommitteeAPIView,
    ReviewerResponseAPIView,
    SubmitReviewDecisionAPIView,
    FetchResearchPaperDetailsAPIView,
    GetAvailableReviewersAPIView
)

urlpatterns = [
    path('papers/<int:paper_id>/committee/create/', CreateCommitteeAPIView.as_view(), name='create-committee'),
    path('members/<int:member_id>/respond/', ReviewerResponseAPIView.as_view(), name='reviewer-respond'),
    path('members/<int:member_id>/decision/', SubmitReviewDecisionAPIView.as_view(), name='submit-decision'),
    path('papers/<int:paper_id>/details/', FetchResearchPaperDetailsAPIView.as_view(), name='paper-details'),
    path('papers/<int:paper_id>/available-reviewers/', GetAvailableReviewersAPIView.as_view(), name='available-reviewers'),
]