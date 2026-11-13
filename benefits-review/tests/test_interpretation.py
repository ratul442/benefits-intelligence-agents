"""Regression tests for comparability-aware validation and country context."""

import json
import unittest

from src.alignment import apply_deterministic_alignment, compute_prevalence_alignment
from src.models import AlignmentRule, DatapointEntry, ReportRow
from src.prompt_builder import _format_catalog, build_topic_messages


def _percentile_datapoint() -> DatapointEntry:
    return DatapointEntry(
        comparison_key="maternity_maximum",
        pretty_name="Maternity maximum",
        benefit_topic="Healthcare",
        company_prompt="Compare the maternity maximum.",
        value_type="amount",
        alignment=AlignmentRule(
            logic="50th Percentile",
            basis="numeric_percentile",
        ),
    )


def _prevalence_datapoint() -> DatapointEntry:
    return DatapointEntry(
        comparison_key="benefit_prevalence",
        pretty_name="Prevalence",
        benefit_topic="Risk Benefits",
        company_prompt="Determine whether the benefit is offered.",
        value_type="free_text",
        alignment=AlignmentRule(
            logic="Prevalence",
            basis="yes_no_prevalence",
        ),
    )


class InterpretationTests(unittest.TestCase):
    def test_not_offered_uses_negative_prevalence_alignment(self):
        cases = (
            ("0% of peers offer benefit", "= Broadly Aligned (0.0%)"),
            ("66.7% of peers offer benefit", "-- Significantly Below (66.7%)"),
        )

        for market_practice, expected in cases:
            with self.subTest(market_practice=market_practice):
                alignment, error = compute_prevalence_alignment(
                    "Not offered",
                    market_practice,
                    _prevalence_datapoint(),
                )

                self.assertEqual(alignment, expected)
                self.assertIsNone(error)

    def test_incompatible_bases_preserve_holistic_alignment(self):
        row = ReportRow(
            comparison_key="maternity_maximum",
            pretty_name="Maternity maximum",
            company_provision="S$5,000 combined annual maximum",
            market_practice="S$3,000 per birth (P50)",
            market_alignment="= Broadly Aligned",
        )

        result = apply_deterministic_alignment([row], [_percentile_datapoint()])[0]

        self.assertEqual(result.market_alignment, "= Broadly Aligned")
        self.assertEqual(result.alignment_source, "llm")
        self.assertEqual(result.validation_status, "passed")

    def test_qualitative_maximum_is_not_a_numeric_failure(self):
        row = ReportRow(
            comparison_key="maternity_maximum",
            pretty_name="Maternity maximum",
            company_provision="No overall maximum",
            market_practice="S$3,000 per birth (P50)",
            market_alignment="++ Significantly Above",
        )

        result = apply_deterministic_alignment([row], [_percentile_datapoint()])[0]

        self.assertEqual(result.alignment_source, "llm")
        self.assertEqual(result.validation_status, "passed")
        self.assertFalse(any("Expected numeric" in error for error in result.validation_errors))

    def test_equivalent_scalar_measure_remains_deterministic(self):
        row = ReportRow(
            comparison_key="maternity_maximum",
            pretty_name="Maternity maximum",
            company_provision="S$5,000 per birth",
            market_practice="S$3,000 per birth (P50)",
            market_alignment="= Broadly Aligned",
        )

        result = apply_deterministic_alignment([row], [_percentile_datapoint()])[0]

        self.assertEqual(result.market_alignment, "++ Significantly Above")
        self.assertEqual(result.alignment_source, "deterministic")
        self.assertEqual(result.validation_status, "corrected")

    def test_missing_holistic_judgment_requires_review(self):
        row = ReportRow(
            comparison_key="maternity_maximum",
            pretty_name="Maternity maximum",
            company_provision="S$5,000 combined annual maximum",
            market_practice="S$3,000 per birth (P50)",
            market_alignment="N/A",
        )

        result = apply_deterministic_alignment([row], [_percentile_datapoint()])[0]

        self.assertEqual(result.validation_status, "review")
        self.assertFalse(result.customer_safe)
        self.assertEqual(result.review_reason_code, "HOLISTIC_ALIGNMENT_REQUIRED")

    def test_singapore_context_is_added_to_system_instructions(self):
        messages = build_topic_messages(
            topic_name="Healthcare",
            company_slice="## Healthcare\nCompany data",
            market_slice="## Healthcare\nMarket data",
            datapoints=[_percentile_datapoint()],
            country="SGP",
        )

        system_message = messages[0]["content"]
        self.assertIn("## COUNTRY CONTEXT", system_message)
        self.assertIn("Country: SGP", system_message)
        self.assertIn("CPF", system_message)
        self.assertIn("do not infer a provision", system_message)

    def test_extraction_instructions_require_factual_scope_and_denominators(self):
        messages = build_topic_messages(
            topic_name="Healthcare",
            company_slice="## Healthcare\nCompany data",
            market_slice="## Healthcare\nMarket data",
            datapoints=[_percentile_datapoint()],
            country="SGP",
        )

        system_message = messages[0]["content"]
        normalized_message = " ".join(system_message.split())
        self.assertIn("Independent datapoint scope", normalized_message)
        self.assertIn("Prompt-completeness check", normalized_message)
        self.assertIn("Exact market basis", normalized_message)
        self.assertIn("No inferred statistics", normalized_message)
        self.assertIn("no evidence from a different benefit", normalized_message)
        self.assertIn("Additional comments", normalized_message)
        self.assertIn("95.8% of organizations with a maximum", normalized_message)
        self.assertIn("Multiple measures and shared limits", normalized_message)
        self.assertIn("every affected individual-service summary", normalized_message)
        self.assertIn("include every measure required", normalized_message)

    def test_catalog_json_preserves_original_glb_prompt_exactly(self):
        original_prompt = (
            "Capture all details:\n"
            "- Option A | denominator: benefit offerers\n"
            "- Option B: 42% of respondents"
        )
        datapoint = _percentile_datapoint().model_copy(
            update={"company_prompt": original_prompt}
        )

        catalog = json.loads(_format_catalog([datapoint]))

        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0]["comparison_key"], "maternity_maximum")
        self.assertEqual(catalog[0]["original_glb_prompt"], original_prompt)


if __name__ == "__main__":
    unittest.main()