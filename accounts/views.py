from django.contrib.auth import update_session_auth_hash
from django.utils import timezone
from rest_framework import status, generics, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django_filters.rest_framework import DjangoFilterBackend
from .models import User, PasswordResetToken
from .permissions import CanManageUsers, IsEmailVerified
from .serializers import (
    RegisterSerializer, LoginSerializer, ProfileSerializer,
    ChangePasswordSerializer, PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer, EmailVerifySerializer,
    UserListSerializer, UserSerializer, UserUpdateSerializer,
)
from .utils import create_token_for_user, verify_token, send_email_verification, send_password_reset_email

class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            raw_token = create_token_for_user(user, token_type='email_verify', expiry_hours=24)
            try:
                send_email_verification(user, raw_token)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to send verification email to {user.email}: {e}")

            return Response({
                'message': 'تم إنشاء حسابك بنجاح. يرجى تأكيد بريدك الإلكتروني.',
                'user': UserSerializer(user).data,
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        raw_token = serializer.validated_data['token']
        token_obj = verify_token(raw_token, token_type='email_verify')

        if not token_obj:
            return Response(
                {'error': 'الرابط غير صالح أو منتهي الصلاحية.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = token_obj.user
        user.email_verified = True
        user.save(update_fields=['email_verified'])

        token_obj.is_used = True
        token_obj.save(update_fields=['is_used'])

        return Response({'message': 'تم تأكيد بريدك الإلكتروني بنجاح. يمكنك الآن تسجيل الدخول.'})


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = serializer.validated_data['user']
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])

            return Response({
                'access': serializer.validated_data['access'],
                'refresh': serializer.validated_data['refresh'],
                'user': UserSerializer(user).data,
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'error': 'refresh token مطلوب.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({'message': 'تم تسجيل الخروج بنجاح.'})
        except TokenError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = ProfileSerializer(request.user)
        return Response(serializer.data)

    def put(self, request):
        return self._update(request, partial=False)

    def patch(self, request):
        return self._update(request, partial=True)

    def _update(self, request, partial):
        serializer = ProfileSerializer(request.user, data=request.data, partial=partial)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response({'message': 'تم تغيير كلمة المرور بنجاح.'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            try:
                user = User.objects.get(email=email, is_active=True)
                raw_token = create_token_for_user(user, token_type='password_reset', expiry_hours=1)
                send_password_reset_email(user, raw_token)
            except User.DoesNotExist:
                pass

            return Response({
                'message': 'إذا كان البريد الإلكتروني مسجلاً، ستتلقى رسالة لإعادة تعيين كلمة المرور.'
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        raw_token = serializer.validated_data['token']
        token_obj = verify_token(raw_token, token_type='password_reset')

        if not token_obj:
            return Response(
                {'error': 'الرابط غير صالح أو منتهي الصلاحية.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = token_obj.user
        user.set_password(serializer.validated_data['new_password'])
        user.save()

        token_obj.is_used = True
        token_obj.save(update_fields=['is_used'])

        return Response({'message': 'تم إعادة تعيين كلمة المرور بنجاح. يمكنك الآن تسجيل الدخول.'})

class AdminUserListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, CanManageUsers]
    serializer_class = UserListSerializer
    queryset = User.objects.all().order_by('-created_at')
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['role', 'is_active', 'email_verified']
    search_fields = ['full_name', 'email', 'institution']
    ordering_fields = ['created_at', 'full_name', 'role']


class AdminUserDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, CanManageUsers]
    queryset = User.objects.all()
    lookup_field = 'user_id'

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return UserUpdateSerializer
        return UserSerializer

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=['is_active'])
        return Response(
            {'message': f'تم تعطيل حساب {user.email} بنجاح.'},
            status=status.HTTP_200_OK
        )


class AdminVerifyEmailView(APIView):
    permission_classes = [IsAuthenticated, CanManageUsers]

    def post(self, request, user_id):
        try:
            user = User.objects.get(user_id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'المستخدم غير موجود.'}, status=status.HTTP_404_NOT_FOUND)

        if user.email_verified:
            return Response({'message': 'البريد الإلكتروني موثق بالفعل.'})

        user.email_verified = True
        user.save(update_fields=['email_verified'])

        return Response({'message': f'تم تأكيد بريد {user.email} بنجاح.'})


class AdminResendVerificationView(APIView):
    permission_classes = [IsAuthenticated, CanManageUsers]

    def post(self, request, user_id):
        try:
            user = User.objects.get(user_id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'المستخدم غير موجود.'}, status=status.HTTP_404_NOT_FOUND)

        if user.email_verified:
            return Response({'message': 'البريد الإلكتروني موثق بالفعل.'})

        raw_token = create_token_for_user(user, token_type='email_verify', expiry_hours=24)
        send_email_verification(user, raw_token)

        return Response({'message': f'تم إرسال بريد التأكيد إلى {user.email}.'})
