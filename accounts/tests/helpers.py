from django.contrib.auth import get_user_model

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
        'email_verified': True,
    }
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)
