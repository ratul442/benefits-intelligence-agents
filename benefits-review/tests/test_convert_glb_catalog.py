"""Tests for authoritative GLB catalog conversion."""

import csv
import tempfile
import unittest
from pathlib import Path

from scripts.convert_glb_catalog import convert_catalog


class ConvertGlbCatalogTests(unittest.TestCase):
    def test_conversion_preserves_keys_prompts_and_order(self):
        columns = [
            "SortOrder",
            "PrimaryName",
            "CountryISO",
            "Topic",
            "BenefitType",
            "ComparisonKey",
            "DatapointName",
            "Prompt",
            "AlignmentLogic",
        ]
        rows = [
            {
                "SortOrder": "2",
                "PrimaryName": "GLB|second",
                "CountryISO": "GLB",
                "Topic": "Healthcare",
                "BenefitType": "Medical",
                "ComparisonKey": "second",
                "DatapointName": "Second",
                "Prompt": "Detailed compound prompt. [Format: F1]",
                "AlignmentLogic": "50th Percentile",
            },
            {
                "SortOrder": "1",
                "PrimaryName": "GLB|first",
                "CountryISO": "GLB",
                "Topic": "Risk Benefits",
                "BenefitType": "Life Insurance",
                "ComparisonKey": "first",
                "DatapointName": "First",
                "Prompt": "Offered status. [Format: F4]",
                "AlignmentLogic": "Prevalence",
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "catalog.csv"
            with source.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                writer.writerows(rows)

            catalog = convert_catalog(source, "glb-v1")

        items = catalog["items"]
        self.assertEqual([item["comparison_key"] for item in items], ["first", "second"])
        self.assertEqual(items[1]["company_prompt"], rows[0]["Prompt"])
        self.assertEqual(items[1]["format_tag"], "F1")
        self.assertEqual(items[1]["value_type"], "free_text")
        self.assertEqual(catalog["total_datapoints"], 2)


if __name__ == "__main__":
    unittest.main()