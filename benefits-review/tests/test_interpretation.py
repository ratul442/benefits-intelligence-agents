"""Regression tests for comparability-aware validation and country context."""

import unittest

from src.alignment import apply_deterministic_alignment
from src.models import AlignmentRule, DatapointEntry, ReportRow
from src.prompt_builder import build_topic_messages


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


class InterpretationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()