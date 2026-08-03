from django.test import SimpleTestCase

from ai_service.ieee_checker.domain.entities import IEEECheckResult, ReferenceEntry
from ai_service.ieee_checker.services.format_validator import (
    calculate_scores,
    compute_ieee_score,
    generate_recommendations,
    generate_summary,
    validate_ieee_format,
)


def _valid_ref(**overrides):
    defaults = dict(
        index=1, raw_text="raw", authors="F. Lastname",
        title="A Great Paper Title", source="IEEE Transactions", year="2021",
        pages="12-20",
    )
    defaults.update(overrides)
    return ReferenceEntry(**defaults)


class ValidateIeeeFormatTests(SimpleTestCase):
    def test_fully_valid_reference_has_no_errors(self):
        self.assertEqual(validate_ieee_format(_valid_ref()), [])

    def test_missing_authors_flagged(self):
        errors = validate_ieee_format(_valid_ref(authors=""))
        self.assertTrue(any("المؤلف" in e for e in errors))

    def test_non_ieee_author_format_flagged_for_latin_names(self):
        errors = validate_ieee_format(_valid_ref(authors="John Smith"))
        self.assertTrue(any("تنسيق المؤلفين" in e for e in errors))

    def test_arabic_author_names_not_flagged_for_ieee_format(self):
        errors = validate_ieee_format(_valid_ref(authors="محمد أحمد"))
        self.assertFalse(any("تنسيق المؤلفين" in e for e in errors))

    def test_missing_title_flagged(self):
        errors = validate_ieee_format(_valid_ref(title=""))
        self.assertTrue(any("عنوان البحث" in e for e in errors))

    def test_invalid_year_format_flagged(self):
        errors = validate_ieee_format(_valid_ref(year="21"))
        self.assertTrue(any("سنة النشر غير صحيحة" in e for e in errors))

    def test_missing_source_and_url_flagged(self):
        errors = validate_ieee_format(_valid_ref(source="", url=""))
        self.assertTrue(any("اسم المجلة" in e for e in errors))

    def test_invalid_doi_format_flagged(self):
        errors = validate_ieee_format(_valid_ref(doi="not-a-doi"))
        self.assertTrue(any("تنسيق DOI" in e for e in errors))

    def test_valid_doi_not_flagged(self):
        errors = validate_ieee_format(_valid_ref(doi="10.1109/EXAMPLE.2021.123"))
        self.assertFalse(any("DOI" in e for e in errors))


class ComputeIeeeScoreTests(SimpleTestCase):
    def test_no_errors_gives_full_score(self):
        self.assertEqual(compute_ieee_score([]), 100.0)

    def test_known_penalty_categories_applied(self):
        self.assertEqual(compute_ieee_score(["مفقود: اسم المؤلف/المؤلفين"]), 75.0)
        self.assertEqual(compute_ieee_score(["مفقودة: سنة النشر"]), 80.0)

    def test_unknown_error_gets_default_penalty(self):
        self.assertEqual(compute_ieee_score(["some unrecognized error string"]), 90.0)

    def test_score_never_goes_below_zero(self):
        errors = ["مفقود: اسم المؤلف/المؤلفين"] * 10
        self.assertEqual(compute_ieee_score(errors), 0.0)


class CalculateScoresTests(SimpleTestCase):
    def test_no_citations_and_no_references_gives_perfect_citation_score(self):
        result = calculate_scores(IEEECheckResult())
        self.assertEqual(result.citation_matching_score, 100.0)

    def test_missing_and_unused_citations_penalized(self):
        result = IEEECheckResult(
            citations_in_text=[1, 2, 3],
            citations_missing_from_references=[3],
            unused_references=[9],
            total_references=1,
        )
        result = calculate_scores(result)
        self.assertEqual(result.citation_matching_score, 85.0)

    def test_format_score_reflects_average_errors_per_reference(self):
        ref = _valid_ref(authors="")
        ref.format_errors = ["مفقود: اسم المؤلف/المؤلفين"]
        result = IEEECheckResult(references=[ref], total_references=1)
        result = calculate_scores(result)
        self.assertEqual(result.format_score, 85.0)

    def test_overall_score_without_crossref_excludes_crossref_weight(self):
        # citation_matching_score/format_score are recomputed by calculate_scores from
        # citations_in_text/references, not taken from the input result as-is - only
        # structure_score is a genuine pass-through value.
        ref = _valid_ref()
        result = IEEECheckResult(
            citations_in_text=[1], references=[ref], total_references=1,
            structure_score=100.0, crossref_checked=0,
        )
        result = calculate_scores(result)
        self.assertEqual(result.citation_matching_score, 100.0)
        self.assertEqual(result.format_score, 100.0)
        self.assertEqual(result.crossref_score, 0.0)
        self.assertEqual(result.overall_score, 100.0)
        self.assertEqual(result.status, "pass")

    def test_overall_score_with_crossref_includes_crossref_weight(self):
        result = IEEECheckResult(
            citations_in_text=[1], references=[], total_references=0,
            structure_score=100.0, crossref_checked=4, crossref_verified_count=2,
        )
        result = calculate_scores(result)
        self.assertEqual(result.citation_matching_score, 100.0)
        self.assertEqual(result.format_score, 0.0)
        self.assertEqual(result.crossref_score, 50.0)
        self.assertEqual(result.overall_score, 62.5)
        self.assertEqual(result.status, "warning")

    def test_status_thresholds(self):
        low = calculate_scores(IEEECheckResult(
            citation_matching_score=0.0, format_score=0.0, structure_score=0.0,
        ))
        self.assertEqual(low.status, "fail")


class GenerateRecommendationsTests(SimpleTestCase):
    def test_no_issues_gives_positive_message(self):
        recs = generate_recommendations(IEEECheckResult(format_score=100.0))
        self.assertEqual(len(recs), 1)
        self.assertIn("ممتاز", recs[0])

    def test_missing_sections_flagged(self):
        result = IEEECheckResult(missing_required_sections=["Abstract", "Conclusion"])
        recs = generate_recommendations(result)
        self.assertTrue(any("أقسام ناقصة" in r for r in recs))

    def test_invalid_section_order_flagged(self):
        result = IEEECheckResult(section_order_valid=False)
        recs = generate_recommendations(result)
        self.assertTrue(any("ترتيب أقسام" in r for r in recs))

    def test_unused_references_flagged(self):
        result = IEEECheckResult(unused_references=[5])
        recs = generate_recommendations(result)
        self.assertTrue(any("[5]" in r for r in recs))


class GenerateSummaryTests(SimpleTestCase):
    def test_summary_contains_key_fields(self):
        result = IEEECheckResult(
            paper_title="My Paper", detected_language="en", total_pages=10,
            total_references=5, structure_score=80.0, overall_score=90.0, status="pass",
        )
        summary = generate_summary(result)
        self.assertIn("My Paper", summary)
        self.assertIn("90.0/100", summary)
        self.assertIn("مقبول", summary)
