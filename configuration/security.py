from configuration.models import JournalConfiguration

def can_user_access_pdf(user, paper):

    is_authenticated = bool(user and user.is_authenticated)

    if is_authenticated and (user.is_staff or user.is_superuser):
        return True

    if is_authenticated and user == paper.author:
        return True

    config = JournalConfiguration.objects.first()
    current_mode = config.system_mode if config else 'full_open'

    if current_mode == 'full_open':
        return True

    if current_mode == 'abstract_only':
        return False

    if current_mode == 'full_closed':

        if is_authenticated and getattr(user, 'has_active_subscription', False):
            return True
        return False

    if current_mode == 'hybrid':

        if paper.is_paid_open_access:
            return True

        if is_authenticated and getattr(user, 'has_active_subscription', False):
            return True
        return False

    return False