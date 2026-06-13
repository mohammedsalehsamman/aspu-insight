from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views


auth_urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='auth-register'),
    path('verify-email/', views.VerifyEmailView.as_view(), name='auth-verify-email'),
    path('login/', views.LoginView.as_view(), name='auth-login'),
    path('logout/', views.LogoutView.as_view(), name='auth-logout'),
    path('refresh/', TokenRefreshView.as_view(), name='auth-token-refresh'),
    path('profile/', views.ProfileView.as_view(), name='auth-profile'),
    path('change-password/', views.ChangePasswordView.as_view(), name='auth-change-password'),
    path('password-reset/', views.PasswordResetRequestView.as_view(), name='auth-password-reset'),
    path('password-reset/confirm/', views.PasswordResetConfirmView.as_view(), name='auth-password-reset-confirm'),
    
    path('2fa/enable/', views.Enable2FAView.as_view(), name='auth-2fa-enable'),
    path('2fa/confirm/', views.Confirm2FAView.as_view(), name='auth-2fa-confirm'),
]

admin_urlpatterns = [
    path('users/', views.AdminUserListView.as_view(), name='admin-user-list'),
    path('users/<int:user_id>/', views.AdminUserDetailView.as_view(), name='admin-user-detail'),
    path('users/<int:user_id>/verify-email/', views.AdminVerifyEmailView.as_view(), name='admin-verify-email'),
    path('users/<int:user_id>/resend-verification/', views.AdminResendVerificationView.as_view(), name='admin-resend-verification'),
]