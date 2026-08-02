"""دوال مساعدة محلية بأسلوب accounts/tests.py (إنشاء مباشر عبر .objects.create)
بدل إدخال تبعية اختبار جديدة مثل factory_boy."""
from django.contrib.auth import get_user_model

from research.models import ResearchPaper

User = get_user_model()

_counter = {'n': 0}


def _next_email(prefix):
    _counter['n'] += 1
    return f"{prefix}{_counter['n']}@example.com"


def make_user(role='author', **kwargs):
    defaults = {
        'email': _next_email(role),
        'full_name': f"مستخدم {role}",
        'password': 'TestPass123!',
        'role': role,
        'specialization': 'علوم الحاسوب',
    }
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


def make_paper(author=None, status=ResearchPaper.Status.SUBMITTED, **kwargs):
    author = author or make_user(role='author')
    defaults = {
        'title': 'بحث تجريبي',
        'abstract': 'ملخص تجريبي للبحث.',
        'author': author,
        'status': status,
        'specialization': 'علوم الحاسوب',
    }
    defaults.update(kwargs)
    return ResearchPaper.objects.create(**defaults)
