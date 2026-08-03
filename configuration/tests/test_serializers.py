from django.test import SimpleTestCase

from configuration.serializers import JournalConfigurationSerializer


class JournalConfigurationSerializerTests(SimpleTestCase):
    def test_valid_system_mode_accepted(self):
        serializer = JournalConfigurationSerializer(data={'system_mode': 'hybrid'})
        self.assertTrue(serializer.is_valid())

    def test_all_documented_choices_are_valid(self):
        for mode, _ in [
            ('full_open', ''), ('full_closed', ''), ('hybrid', ''), ('abstract_only', ''),
        ]:
            serializer = JournalConfigurationSerializer(data={'system_mode': mode})
            self.assertTrue(serializer.is_valid(), msg=f'{mode} should be valid')

    def test_invalid_system_mode_rejected(self):
        serializer = JournalConfigurationSerializer(data={'system_mode': 'not_a_real_mode'})
        self.assertFalse(serializer.is_valid())
        self.assertIn('system_mode', serializer.errors)

    def test_missing_system_mode_is_valid_because_model_field_has_a_default(self):
        # ModelSerializer marks a field as not required when the underlying model
        # field declares a default, so omitting system_mode is accepted even on a
        # non-partial serializer and falls back to 'full_open'.
        serializer = JournalConfigurationSerializer(data={})
        self.assertTrue(serializer.is_valid())

    def test_partial_update_allows_missing_fields(self):
        serializer = JournalConfigurationSerializer(data={}, partial=True)
        self.assertTrue(serializer.is_valid())
