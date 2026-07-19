from django.urls import path

from configuration.views import AdminJournalConfigurationView

urlpatterns = [
    path('', AdminJournalConfigurationView.as_view(), name='admin-journal-configuration'),
]
