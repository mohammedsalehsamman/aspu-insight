from rest_framework import serializers

from configuration.models import JournalConfiguration

class JournalConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalConfiguration
        fields = ['id', 'system_mode']
