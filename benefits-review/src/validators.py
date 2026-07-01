"""Validate parsed report rows against business rules."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.models import DatapointEntry, ReportRow

_VALID_ALIGNMENT_PREFIXES = {"++", "+", "=", "-", "--", "N/A"}


@dataclass
class ValidationResult:
    """Result of validating a set of report rows."""

    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_rows(
    rows: list[ReportRow],
    expected_datapoints: list[DatapointEntry] | None = None,
) -> ValidationResult:
    """Validate output rows against format and business rules.

    Checks:
    1. No empty fields (except valid "N/A" or "Not Provided")
    2. Alignment column uses valid tier indicators
    3. Prevalence rows include percentage in alignment
    4. No internal plan names (e.g. "Plans: 01 Healthcare")
    5. Expected datapoints are present (if catalog provided)
    """
    result = ValidationResult()

    for i, row in enumerate(rows):
        row_label = f"Row {i + 1} ({row.comparison_key})"

        # Check for empty fields
        if not row.comparison_key:
            result.errors.append(f"{row_label}: empty comparison_key")
            result.is_valid = False

        if not row.pretty_name:
            result.errors.append(f"{row_label}: empty pretty_name")
            result.is_valid = False

        # Validate alignment format
        alignment = row.market_alignment.strip()
        if alignment and alignment != "N/A" and alignment != "Not Provided":
            prefix = alignment.split(" ")[0]
            if prefix not in _VALID_ALIGNMENT_PREFIXES:
                result.warnings.append(
                    f"{row_label}: unexpected alignment prefix '{prefix}'"
                )

        # Check for plan names leaking into output
        if "Plans:" in row.company_provision or "Plans:" in row.market_practice:
            result.errors.append(f"{row_label}: internal plan name found in output")
            result.is_valid = False

        # Validate N/A rule: if alignment is N/A, ALL fields should be N/A
        if alignment == "N/A":
            if row.company_provision != "N/A" or row.market_practice != "N/A":
                result.warnings.append(
                    f"{row_label}: alignment is N/A but other fields are not"
                )

    # Check completeness against catalog
    if expected_datapoints:
        expected_keys = {dp.comparison_key for dp in expected_datapoints}
        actual_keys = {r.comparison_key for r in rows}
        missing = expected_keys - actual_keys
        if missing:
            result.warnings.append(
                f"Missing {len(missing)} datapoints: {sorted(missing)[:5]}..."
            )

        # Validate prevalence formatting
        dp_lookup = {dp.comparison_key: dp for dp in expected_datapoints}
        for row in rows:
            dp = dp_lookup.get(row.comparison_key)
            if dp and dp.alignment_logic == "Prevalence":
                alignment = row.market_alignment
                if alignment not in ("N/A", "Not Provided") and "%" not in alignment:
                    result.warnings.append(
                        f"Row ({row.comparison_key}): Prevalence alignment missing percentage"
                    )

    return result
