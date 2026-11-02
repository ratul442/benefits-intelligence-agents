"""Convert an authoritative GLB datapoint CSV to the agent catalog schema."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

REQUIRED_COLUMNS = {
    "SortOrder",
    "PrimaryName",
    "CountryISO",
    "Topic",
    "BenefitType",
    "ComparisonKey",
    "DatapointName",
    "Prompt",
    "AlignmentLogic",
}


def _format_tag(prompt: str) -> str:
    match = re.search(r"\[Format:\s*(F\d+)\]", prompt, re.IGNORECASE)
    return match.group(1).upper() if match else "F4"


def _alignment(logic: str) -> dict[str, object]:
    if logic == "50th Percentile":
        return {"logic": logic, "basis": "numeric_percentile"}
    if logic == "Prevalence":
        return {
            "logic": logic,
            "basis": "yes_no_prevalence",
            "positive_option": "Yes",
        }
    raise ValueError(f"Unsupported AlignmentLogic: {logic!r}")


def convert_catalog(source: Path, version: str) -> dict[str, object]:
    """Convert CSV rows one-to-one without splitting or consolidating them."""
    with source.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        missing_columns = REQUIRED_COLUMNS.difference(reader.fieldnames or [])
        if missing_columns:
            raise ValueError(f"Missing required columns: {sorted(missing_columns)}")
        rows = list(reader)

    keys = [row["ComparisonKey"].strip() for row in rows]
    if any(not key for key in keys):
        raise ValueError("ComparisonKey must not be blank")
    duplicate_keys = sorted({key for key in keys if keys.count(key) > 1})
    if duplicate_keys:
        raise ValueError(f"Duplicate ComparisonKey values: {duplicate_keys}")

    items = []
    for row in sorted(rows, key=lambda item: int(item["SortOrder"])):
        logic = row["AlignmentLogic"].strip()
        items.append(
            {
                "comparison_key": row["ComparisonKey"].strip(),
                "pretty_name": row["DatapointName"].strip(),
                "benefit_topic": row["Topic"].strip(),
                "company_prompt": row["Prompt"].strip(),
                "value_type": "free_text",
                "alignment": _alignment(logic),
                "format_tag": _format_tag(row["Prompt"]),
                "source_sort_order": int(row["SortOrder"]),
                "source_primary_name": row["PrimaryName"].strip(),
                "source_country_iso": row["CountryISO"].strip(),
                "source_benefit_type": row["BenefitType"].strip(),
                "output_rules": {
                    "allow_not_provided": True,
                    "dual_blank_outputs_na": True,
                    "suppress_plan_names": True,
                    "no_literal_line_breaks": True,
                },
            }
        )

    return {
        "catalog_id": "glb-benefit-datapoints",
        "catalog_version": version,
        "country": "GLB",
        "source_file": source.name,
        "total_datapoints": len(items),
        "items": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--expected-count", type=int, default=160)
    args = parser.parse_args()

    catalog = convert_catalog(args.source, args.version)
    if catalog["total_datapoints"] != args.expected_count:
        raise ValueError(
            f"Expected {args.expected_count} rows, got {catalog['total_datapoints']}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    print(
        f"Converted {catalog['total_datapoints']} rows from {args.source.name} "
        f"to {args.output}"
    )


if __name__ == "__main__":
    main()