from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from ai_service.utils.embeddings import get_embedding_model


class GetEmbeddingModelTests(SimpleTestCase):
    def setUp(self):
        get_embedding_model.cache_clear()

    def tearDown(self):
        get_embedding_model.cache_clear()

    def test_same_model_name_returns_cached_instance(self):
        with patch("sentence_transformers.SentenceTransformer") as mock_cls:
            mock_cls.return_value = MagicMock()
            first = get_embedding_model("some/model-name")
            second = get_embedding_model("some/model-name")
        self.assertIs(first, second)
        mock_cls.assert_called_once_with("some/model-name")

    def test_different_model_names_construct_separately(self):
        with patch("sentence_transformers.SentenceTransformer") as mock_cls:
            mock_cls.side_effect = [MagicMock(), MagicMock()]
            first = get_embedding_model("model-a")
            second = get_embedding_model("model-b")
        self.assertIsNot(first, second)
        self.assertEqual(mock_cls.call_count, 2)

    @override_settings(CLAIM_EVIDENCE_EMBEDDING_MODEL="configured/default-model")
    def test_falls_back_to_settings_when_no_name_given(self):
        with patch("sentence_transformers.SentenceTransformer") as mock_cls:
            mock_cls.return_value = MagicMock()
            get_embedding_model()
        mock_cls.assert_called_once_with("configured/default-model")
