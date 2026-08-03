from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from ai_service.ieee_checker.infrastructure import nlp_models


class GetExtractionLlmTests(SimpleTestCase):
    def setUp(self):
        nlp_models._llm_model = None
        nlp_models._llm_tokenizer = None

    def tearDown(self):
        nlp_models._llm_model = None
        nlp_models._llm_tokenizer = None

    def test_calling_twice_only_constructs_model_once(self):
        fake_model = MagicMock()
        fake_tokenizer = MagicMock()
        with patch("transformers.AutoModelForCausalLM.from_pretrained", return_value=fake_model) as mock_model, \
             patch("transformers.AutoTokenizer.from_pretrained", return_value=fake_tokenizer) as mock_tok:
            first_model, first_tok = nlp_models.get_extraction_llm()
            second_model, second_tok = nlp_models.get_extraction_llm()
        self.assertIs(first_model, second_model)
        self.assertIs(first_tok, second_tok)
        mock_model.assert_called_once()
        mock_tok.assert_called_once()
        fake_model.eval.assert_called_once()

    @override_settings(IEEE_CHECKER_LLM_MODEL="configured/llm-model")
    def test_configured_model_name_passed_through(self):
        with patch("transformers.AutoModelForCausalLM.from_pretrained", return_value=MagicMock()) as mock_model, \
             patch("transformers.AutoTokenizer.from_pretrained", return_value=MagicMock()) as mock_tok:
            nlp_models.get_extraction_llm()
        mock_tok.assert_called_once_with("configured/llm-model")
        self.assertEqual(mock_model.call_args.args[0], "configured/llm-model")


class GetNerPipelineTests(SimpleTestCase):
    def setUp(self):
        nlp_models._ner_pipeline = None

    def tearDown(self):
        nlp_models._ner_pipeline = None

    def test_calling_twice_only_constructs_pipeline_once(self):
        with patch("transformers.pipeline") as mock_pipeline:
            mock_pipeline.return_value = MagicMock()
            first = nlp_models.get_ner_pipeline()
            second = nlp_models.get_ner_pipeline()
        self.assertIs(first, second)
        mock_pipeline.assert_called_once()

    @override_settings(IEEE_CHECKER_NER_MODEL="configured/ner-model")
    def test_configured_model_name_passed_through(self):
        with patch("transformers.pipeline") as mock_pipeline:
            mock_pipeline.return_value = MagicMock()
            nlp_models.get_ner_pipeline()
        mock_pipeline.assert_called_once_with(
            "ner",
            model="configured/ner-model",
            aggregation_strategy="simple",
            device=-1,
        )
