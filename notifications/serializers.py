from rest_framework import serializers

from notifications.models import Notification


class NotificationActorSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    full_name = serializers.CharField()
    role = serializers.CharField()


class NotificationSerializer(serializers.ModelSerializer):
    actor = NotificationActorSerializer(read_only=True)
    target_type = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id', 'notification_type', 'level', 'title', 'body', 'data',
            'actor', 'target_type', 'target_object_id', 'target_repr',
            'group_key', 'is_read', 'read_at', 'created_at',
        ]
        read_only_fields = fields

    def get_target_type(self, obj):
        return obj.target_content_type.model if obj.target_content_type_id else None
