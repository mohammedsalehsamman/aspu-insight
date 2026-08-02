from rest_framework import serializers

from notifications.models import Notification
from notifications.services import NON_DISABLEABLE_IN_APP


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


class NotificationPreferenceSerializer(serializers.Serializer):
    """يمثّل قيم القنوات لنوع إشعار واحد — نفس الشكل للقراءة (كل الأنواع، فعّالة افتراضياً أو
    مخصَّصة) وللكتابة (الأنواع المُرسَلة فقط؛ الحقول الغائبة تبقى على قيمتها الفعّالة الحالية)."""

    notification_type = serializers.ChoiceField(choices=Notification.NotificationType.choices)
    non_disableable = serializers.BooleanField(read_only=True)
    in_app_enabled = serializers.BooleanField(required=False)
    email_enabled = serializers.BooleanField(required=False)
    push_enabled = serializers.BooleanField(required=False)

    def validate(self, attrs):
        # خط الأمان الثاني (الأول في NotificationService وقت القراءة/الإرسال) — لا يمكن لأي
        # مدخل من العميل إسكات in_app لنوع حرج، حتى لو مرّ بالخطأ من هنا.
        if attrs.get('notification_type') in NON_DISABLEABLE_IN_APP:
            attrs['in_app_enabled'] = True
        return attrs
