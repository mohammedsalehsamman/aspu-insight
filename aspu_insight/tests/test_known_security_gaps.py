from django.test import TestCase
from django.urls import NoReverseMatch, reverse


class SwaggerDocsHiddenInProductionTests(TestCase):
    """C2 fix: SpectacularAPIView/SwaggerView/RedocView are now registered only inside the
    `if settings.DEBUG:` block in aspu_insight/urls.py (same pattern already used for
    media/static), instead of being world-readable regardless of DEBUG. The test suite runs
    with DEBUG=False (see .env / aspu_insight/settings.py), matching a production deployment."""

    def test_schema_url_name_does_not_resolve(self):
        with self.assertRaises(NoReverseMatch):
            reverse('schema')

    def test_swagger_ui_url_name_does_not_resolve(self):
        with self.assertRaises(NoReverseMatch):
            reverse('swagger-ui')

    def test_redoc_url_name_does_not_resolve(self):
        with self.assertRaises(NoReverseMatch):
            reverse('redoc')

    def test_docs_path_returns_404(self):
        response = self.client.get('/api/docs/')
        self.assertEqual(response.status_code, 404)

    def test_schema_path_returns_404(self):
        response = self.client.get('/api/schema/schemaAspu2004/')
        self.assertEqual(response.status_code, 404)
