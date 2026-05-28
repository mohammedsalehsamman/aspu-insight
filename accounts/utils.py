import hashlib
import secrets
import uuid
from datetime import timedelta

from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone


def generate_secure_token():
    return secrets.token_urlsafe(64)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_token_for_user(user, token_type: str, expiry_hours: int = 24):
    from .models import PasswordResetToken
    PasswordResetToken.objects.filter(
        user=user,
        token_type=token_type,
        is_used=False
    ).update(is_used=True)

    raw_token = generate_secure_token()
    token_hash = hash_token(raw_token)
    expires_at = timezone.now() + timedelta(hours=expiry_hours)

    PasswordResetToken.objects.create(
        user=user,
        token_hash=token_hash,
        token_type=token_type,
        expires_at=expires_at,
    )

    return raw_token


def verify_token(raw_token: str, token_type: str):
    from .models import PasswordResetToken

    token_hash = hash_token(raw_token)
    try:
        token_obj = PasswordResetToken.objects.get(
            token_hash=token_hash,
            token_type=token_type,
            is_used=False,
        )
        if token_obj.is_valid():
            return token_obj
        return None
    except PasswordResetToken.DoesNotExist:
        return None


def send_email_verification(user, raw_token: str):
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    verify_url = f"{frontend_url}/verify-email?token={raw_token}"

    subject = 'تأكيد بريدك الإلكتروني - ASPU Insight'
    message = f"""
مرحباً {user.full_name}،

شكراً لتسجيلك في منصة ASPU Insight للبحث العلمي.

لتفعيل حسابك، يرجى النقر على الرابط التالي:
{verify_url}

هذا الرابط صالح لمدة 24 ساعة فقط.

إذا لم تقم بإنشاء هذا الحساب، يمكنك تجاهل هذا البريد.

مع تحيات،
 ASPU Insight
    """.strip()

    html_message = f"""
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><meta charset="UTF-8"></head>
<body style="font-family: Arial, sans-serif; direction: rtl; text-align: right;">
  <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
    <h2 style="color: #1a237e;">مرحباً {user.full_name}،</h2>
    <p>شكراً لتسجيلك في منصة <strong>ASPU Insight</strong> للبحث العلمي.</p>
    <p>لتفعيل حسابك، يرجى الضغط على الزر أدناه:</p>
    <div style="text-align: center; margin: 30px 0;">
      <a href="{verify_url}"
         style="background-color: #1a237e; color: white; padding: 12px 24px;
                text-decoration: none; border-radius: 5px; font-size: 16px;">
        تأكيد البريد الإلكتروني
      </a>
    </div>
    <p style="color: #666; font-size: 12px;">هذا الرابط صالح لمدة 24 ساعة فقط.</p>
    <p style="color: #666; font-size: 12px;">إذا لم تقم بإنشاء هذا الحساب، يمكنك تجاهل هذا البريد.</p>
    <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 20px 0;">
    <p style="color: #999; font-size: 11px; text-align: center;"> ASPU Insight</p>
  </div>
</body>
</html>
    """.strip()

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
    )


def send_password_reset_email(user, raw_token: str):
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    reset_url = f"{frontend_url}/reset-password?token={raw_token}"

    subject = 'إعادة تعيين كلمة المرور - ASPU Insight'
    message = f"""
مرحباً {user.full_name}،

تلقينا طلباً لإعادة تعيين كلمة المرور لحسابك في ASPU Insight.

لإعادة تعيين كلمة المرور، انقر على الرابط التالي:
{reset_url}

هذا الرابط صالح لمدة ساعة واحدة فقط.

إذا لم تطلب إعادة تعيين كلمة المرور، يرجى تجاهل هذا البريد.

مع تحيات،
 ASPU Insight
    """.strip()

    html_message = f"""
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><meta charset="UTF-8"></head>
<body style="font-family: Arial, sans-serif; direction: rtl; text-align: right;">
  <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
    <h2 style="color: #1a237e;">مرحباً {user.full_name}،</h2>
    <p>تلقينا طلباً لإعادة تعيين كلمة المرور لحسابك في <strong>ASPU Insight</strong>.</p>
    <p>انقر على الزر أدناه لإعادة تعيين كلمة المرور:</p>
    <div style="text-align: center; margin: 30px 0;">
      <a href="{reset_url}"
         style="background-color: #c62828; color: white; padding: 12px 24px;
                text-decoration: none; border-radius: 5px; font-size: 16px;">
        إعادة تعيين كلمة المرور
      </a>
    </div>
    <p style="color: #666; font-size: 12px;">هذا الرابط صالح لمدة <strong>ساعة واحدة</strong> فقط.</p>
    <p style="color: #666; font-size: 12px;">إذا لم تطلب هذا، تجاهل هذا البريد - حسابك بأمان.</p>
    <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 20px 0;">
    <p style="color: #999; font-size: 11px; text-align: center;"> ASPU Insight</p>
  </div>
</body>
</html>
    """.strip()

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
    )
