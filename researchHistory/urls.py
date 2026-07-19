from django.urls import path

from researchHistory.views import AdminResearchHistoryListView

urlpatterns = [
    path('', AdminResearchHistoryListView.as_view(), name='admin-research-history-list'),
]
