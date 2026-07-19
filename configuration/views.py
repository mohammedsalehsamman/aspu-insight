from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from accounts.permissions import IsAdmin
from configuration.models import JournalConfiguration
from configuration.serializers import JournalConfigurationSerializer


class AdminJournalConfigurationView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_object(self):
        config, _ = JournalConfiguration.objects.get_or_create(pk=1)
        return config

    def get(self, request):
        serializer = JournalConfigurationSerializer(self.get_object())
        return Response(serializer.data)

    def put(self, request):
        return self._update(request, partial=False)

    def patch(self, request):
        return self._update(request, partial=True)

    def _update(self, request, partial):
        serializer = JournalConfigurationSerializer(self.get_object(), data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
