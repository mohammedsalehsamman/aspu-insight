from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User, PasswordResetToken


class UserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = [
            'user_id', 'full_name', 'email', 'role',
            'institution', 'orcid_id', 'profile_picture_url',
            'bio', 'preferred_language', 'is_active',
            'email_verified', 'created_at', 'updated_at', 'last_login',
        ]
        read_only_fields = ['user_id', 'email', 'created_at', 'updated_at', 'last_login']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True, label='تأكيد كلمة المرور')

    class Meta:
        model = User
        fields = [
            'full_name', 'email', 'password', 'password2',
            'role', 'institution', 'orcid_id', 'preferred_language', 'bio',
        ]
        extra_kwargs = {
            'role': {'default': 'author'},
            'institution': {'required': False},
            'orcid_id': {'required': False},
            'preferred_language': {'required': False},
            'bio': {'required': False},
        }

    def validate_email(self, value):
        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError('هذا البريد الإلكتروني مستخدم بالفعل.')
        return value.lower()

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password2'):
            raise serializers.ValidationError({'password': 'كلمتا المرور غير متطابقتين.'})
        if attrs.get('role') == 'admin':
            raise serializers.ValidationError({'role': 'لا يمكنك التسجيل بدور مدير النظام.'})
        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            full_name=validated_data['full_name'],
            password=validated_data['password'],
            role=validated_data.get('role', 'author'),
            institution=validated_data.get('institution', ''),
            orcid_id=validated_data.get('orcid_id', ''),
            preferred_language=validated_data.get('preferred_language', 'ar'),
            bio=validated_data.get('bio', ''),
            email_verified=False,
            is_active=True,
        )
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get('email', '').lower()
        password = attrs.get('password', '')

        user = authenticate(request=self.context.get('request'), email=email, password=password)

        if not user:
            raise serializers.ValidationError('البريد الإلكتروني أو كلمة المرور غير صحيحة.')

        if not user.is_active:
            raise serializers.ValidationError('هذا الحساب معطل. تواصل مع الإدارة.')

        return {
            'user': user,
        }


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'user_id', 'full_name', 'institution', 'orcid_id',
            'profile_picture_url', 'bio', 'preferred_language',
            'email', 'role', 'email_verified', 'created_at', 'updated_at',
        ]
        read_only_fields = ['user_id', 'email', 'role', 'email_verified', 'created_at', 'updated_at']


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('كلمة المرور الحالية غير صحيحة.')
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'new_password': 'كلمتا المرور الجديدتان غير متطابقتين.'})
        return attrs

    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.lower()


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'new_password': 'كلمتا المرور غير متطابقتين.'})
        return attrs


class EmailVerifySerializer(serializers.Serializer):
    token = serializers.CharField()


class UserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'user_id', 'full_name', 'email', 'role',
            'institution', 'is_active','specialization', 'email_verified',
            'created_at', 'last_login'
        ]


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'full_name', 'role', 'institution', 'orcid_id',
            'profile_picture_url', 'bio', 'preferred_language',
            'is_active', 'email_verified',
        ]
