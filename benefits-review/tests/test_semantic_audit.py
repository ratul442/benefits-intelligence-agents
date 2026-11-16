"""Tests for evidence-backed semantic completeness corrections."""

import unittest

from src.models import ReportRow
from src.semantic_audit import apply_semantic_audits


def _row(key: str, company: str = "Initial company", market: str = "Initial market"):
    return ReportRow(
        comparison_key=key,
        pretty_name=key,
        company_provision=company,
        market_practice=market,
        market_alignment="N/A",
    )


class SemanticAuditTests(unittest.TestCase):
    def test_applies_correction_when_quotes_exist_in_corresponding_evidence(self):
        rows = [_row("business_travel")]
        company_evidence = "Maximum out-of-country medical benefit of 10,000,000."
        market_evidence = "Median accidental death benefit amount is 300,000."
        audits = [{
            "comparison_key": "business_travel",
            "status": "corrected",
            "company_provision": "Out-of-country medical maximum: 10,000,000",
            "market_practice": "Median accidental-death benefit: 300,000",
            "missing_facts": ["company medical maximum", "market death benefit"],
            "company_evidence_quotes": [company_evidence],
            "market_evidence_quotes": [market_evidence],
        }]

        result = apply_semantic_audits(
            rows, audits, company_evidence, market_evidence
        )

        self.assertEqual(result.rows[0].validation_status, "corrected")
        self.assertIn("10,000,000", result.rows[0].company_provision)
        self.assertIn("300,000", result.rows[0].market_practice)
        self.assertEqual(result.recovered_facts, 2)
        self.assertEqual(result.unsupported_corrections, 0)

    def test_rejects_correction_when_quote_is_not_in_source(self):
        rows = [_row("healthcare")]
        audits = [{
            "comparison_key": "healthcare",
            "status": "corrected",
            "company_provision": "Initial company",
            "market_practice": "Invented denominator",
            "missing_facts": ["denominator"],
            "company_evidence_quotes": [],
            "market_evidence_quotes": ["This quotation is absent"],
        }]

        result = apply_semantic_audits(
            rows, audits, "Company evidence", "Market evidence"
        )

        self.assertEqual(result.rows[0].market_practice, "Initial market")
        self.assertEqual(result.rows[0].validation_status, "review")
        self.assertEqual(
            result.rows[0].review_reason_code,
            "UNSUPPORTED_SEMANTIC_CORRECTION",
        )
        self.assertEqual(result.unsupported_corrections, 1)

    def test_preserves_shared_limit_in_individual_service_correction(self):
        rows = [_row("normal_delivery", "Offered", "Market fact")]
        company_evidence = (
            "Normal delivery is covered under a shared S$5,000 combined annual "
            "maternity maximum."
        )
        audits = [{
            "comparison_key": "normal_delivery",
            "status": "corrected",
            "company_provision": (
                "Normal delivery offered under shared S$5,000 annual maximum"
            ),
            "market_practice": "Market fact",
            "missing_facts": ["shared annual maximum"],
            "company_evidence_quotes": [company_evidence],
            "market_evidence_quotes": [],
        }]

        result = apply_semantic_audits(rows, audits, company_evidence, "")

        self.assertIn("S$5,000", result.rows[0].company_provision)
        self.assertEqual(result.rows[0].validation_status, "corrected")


if __name__ == "__main__":
    unittest.main()
