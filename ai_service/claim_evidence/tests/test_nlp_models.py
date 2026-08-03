from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from ai_service.claim_evidence.infrastructure import nlp_models
from ai_service.utils.embeddings import get_embedding_model as _shared_get_embedding_model


class GetEmbeddingModelTests(SimpleTestCase):
    def setUp(self):
        _shared_get_embedding_model.cache_clear()

    def tearDown(self):
        _shared_get_embedding_model.cache_clear()

    def test_calling_twice_only_constructs_model_once(self):
        with patch("sentence_transformers.SentenceTransformer") as mock_cls:
            mock_cls.return_value = MagicMock()
            first = nlp_models.get_embedding_model()
            second = nlp_models.get_embedding_model()
        self.assertIs(first, second)
        mock_cls.assert_called_once()

    @override_settings(CLAIM_EVIDENCE_EMBEDDING_MODEL="configured/claim-evidence-model")
    def test_configured_model_name_passed_through(self):
        with patch("sentence_transformers.SentenceTransformer") as mock_cls:
            mock_cls.return_value = MagicMock()
            nlp_models.get_embedding_model()
        mock_cls.assert_called_once_with("configured/claim-evidence-model")


class GetZeroShotClassifierTests(SimpleTestCase):
    def setUp(self):
        nlp_models._zero_shot_classifier = None

    def tearDown(self):
        nlp_models._zero_shot_classifier = None

    def test_calling_twice_only_constructs_pipeline_once(self):
        with patch("transformers.pipeline") as mock_pipeline:
            mock_pipeline.return_value = MagicMock()
            first = nlp_models.get_zero_shot_classifier()
            second = nlp_models.get_zero_shot_classifier()
        self.assertIs(first, second)
        mock_pipeline.assert_called_once()

    @override_settings(CLAIM_EVIDENCE_ZERO_SHOT_MODEL="configured/zero-shot-model")
    def test_configured_model_name_passed_through(self):
        with patch("transformers.pipeline") as mock_pipeline:
            mock_pipeline.return_value = MagicMock()
            nlp_models.get_zero_shot_classifier()
        mock_pipeline.assert_called_once_with(
            "zero-shot-classification",
            model="configured/zero-shot-model",
            device=-1,
        )
