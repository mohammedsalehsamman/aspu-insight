from django.test import TestCase, override_settings

from configuration.models import JournalConfiguration


class JournalConfigurationModelTests(TestCase):
    def test_default_system_mode_is_full_open(self):
        config = JournalConfiguration.objects.create()
        self.assertEqual(config.system_mode, 'full_open')

    def test_str_representation_includes_display_value(self):
        config = JournalConfiguration.objects.create(system_mode='hybrid')
        self.assertIn(config.get_system_mode_display(), str(config))

    def test_multiple_rows_can_technically_be_created(self):
        # Nothing on the model enforces a true singleton at the DB level;
        # the singleton behavior is only enforced by the view's get_or_create(pk=1).
        JournalConfiguration.objects.create(system_mode='full_open')
        JournalConfiguration.objects.create(system_mode='full_closed')
        self.assertEqual(JournalConfiguration.objects.count(), 2)
