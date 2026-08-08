from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from configuration.models import JournalConfiguration
from configuration.security import can_user_access_pdf
from research.models import ResearchPaper

User = get_user_model()


def make_user(email, role, **kwargs):
    return User.objects.create(email=email, full_name=email.split('@')[0], role=role, specialization='law', **kwargs)


class CanUserAccessPdfTests(TestCase):
    def setUp(self):
        self.author = make_user('author@example.com', 'author')
        self.other_user = make_user('other@example.com', 'reader')
        self.staff_user = make_user('staff@example.com', 'reader', is_staff=True)
        self.superuser = make_user('super@example.com', 'reader', is_superuser=True)
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
            status=ResearchPaper.Status.PUBLISHED,
        )
        self.anon = AnonymousUser()

    # --- overrides that apply regardless of system_mode ---

    def test_staff_always_allowed(self):
        JournalConfiguration.objects.create(system_mode='abstract_only')
        self.assertTrue(can_user_access_pdf(self.staff_user, self.paper))

    def test_superuser_always_allowed(self):
        JournalConfiguration.objects.create(system_mode='full_closed')
        self.assertTrue(can_user_access_pdf(self.superuser, self.paper))

    def test_author_always_allowed(self):
        JournalConfiguration.objects.create(system_mode='abstract_only')
        self.assertTrue(can_user_access_pdf(self.author, self.paper))

    # --- no config row present ---

    def test_defaults_to_full_open_when_no_config_exists(self):
        self.assertFalse(JournalConfiguration.objects.exists())
        self.assertTrue(can_user_access_pdf(self.anon, self.paper))

    # --- full_open ---

    def test_full_open_allows_anonymous(self):
        JournalConfiguration.objects.create(system_mode='full_open')
        self.assertTrue(can_user_access_pdf(self.anon, self.paper))

    def test_full_open_allows_authenticated_non_author(self):
        JournalConfiguration.objects.create(system_mode='full_open')
        self.assertTrue(can_user_access_pdf(self.other_user, self.paper))

    # --- abstract_only ---

    def test_abstract_only_denies_authenticated_non_author(self):
        JournalConfiguration.objects.create(system_mode='abstract_only')
        self.assertFalse(can_user_access_pdf(self.other_user, self.paper))

    def test_abstract_only_denies_anonymous(self):
        JournalConfiguration.objects.create(system_mode='abstract_only')
        self.assertFalse(can_user_access_pdf(self.anon, self.paper))

    # --- full_closed ---

    def test_full_closed_denies_anonymous(self):
        JournalConfiguration.objects.create(system_mode='full_closed')
        self.assertFalse(can_user_access_pdf(self.anon, self.paper))

    def test_full_closed_denies_authenticated_without_subscription(self):
        JournalConfiguration.objects.create(system_mode='full_closed')
        self.assertFalse(can_user_access_pdf(self.other_user, self.paper))

    def test_full_closed_allows_authenticated_with_active_subscription(self):
        JournalConfiguration.objects.create(system_mode='full_closed')
        self.other_user.has_active_subscription = True
        self.assertTrue(can_user_access_pdf(self.other_user, self.paper))

    # --- hybrid ---

    def test_hybrid_allows_anonymous_when_paper_is_paid_open_access(self):
        JournalConfiguration.objects.create(system_mode='hybrid')
        self.paper.is_paid_open_access = True
        self.paper.save()
        self.assertTrue(can_user_access_pdf(self.anon, self.paper))

    def test_hybrid_denies_non_subscribed_when_paper_not_open_access(self):
        JournalConfiguration.objects.create(system_mode='hybrid')
        self.assertFalse(can_user_access_pdf(self.other_user, self.paper))

    def test_hybrid_allows_subscribed_user_when_paper_not_open_access(self):
        JournalConfiguration.objects.create(system_mode='hybrid')
        self.other_user.has_active_subscription = True
        self.assertTrue(can_user_access_pdf(self.other_user, self.paper))

    def test_hybrid_denies_anonymous_when_paper_not_open_access(self):
        JournalConfiguration.objects.create(system_mode='hybrid')
        self.assertFalse(can_user_access_pdf(self.anon, self.paper))

    # --- unknown mode fallback ---

    def test_unknown_mode_denies_by_default(self):
        config = JournalConfiguration.objects.create(system_mode='full_open')
        JournalConfiguration.objects.filter(pk=config.pk).update(system_mode='some_future_mode')
        self.assertFalse(can_user_access_pdf(self.other_user, self.paper))

    # --- unpublished papers are never exposed via system_mode, regardless of mode ---

    def test_full_open_denies_non_published_paper_for_anonymous(self):
        JournalConfiguration.objects.create(system_mode='full_open')
        self.paper.status = ResearchPaper.Status.PENDING
        self.paper.save(update_fields=['status'])
        self.assertFalse(can_user_access_pdf(self.anon, self.paper))

    def test_full_open_denies_non_published_paper_for_authenticated_non_author(self):
        JournalConfiguration.objects.create(system_mode='full_open')
        self.paper.status = ResearchPaper.Status.REJECTED
        self.paper.save(update_fields=['status'])
        self.assertFalse(can_user_access_pdf(self.other_user, self.paper))

    def test_author_still_allowed_on_non_published_paper(self):
        JournalConfiguration.objects.create(system_mode='full_open')
        self.paper.status = ResearchPaper.Status.PENDING
        self.paper.save(update_fields=['status'])
        self.assertTrue(can_user_access_pdf(self.author, self.paper))


class HasActiveSubscriptionIsDeadCodeTests(TestCase):

    def test_real_user_never_has_the_has_active_subscription_attribute(self):
        user = make_user('subscriber@example.com', 'reader')
        user.refresh_from_db()
        self.assertFalse(
            getattr(user, 'has_active_subscription', False),
            "A real User instance has a truthy has_active_subscription — if a real "
            "subscription mechanism was added, update the monkey-patched tests above to use "
            "it instead of assigning the attribute by hand."
        )
