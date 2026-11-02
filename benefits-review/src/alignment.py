"""Deterministic alignment scoring — replaces LLM-generated alignment.

Prevalence rules (Company Yes/No vs Market %):
    Company=Yes, Market <25%  → ++ Significantly Above
    Company=Yes, Market 25-49% → + Somewhat Above
    Company=Yes, Market ≥50%  → = Broadly Aligned
    Company=No,  Market <25%  → = Broadly Aligned
    Company=No,  Market 25-49% → - Somewhat Below
    Company=No,  Market ≥50%  → -- Significantly Below

50th Percentile rules (Company numeric vs Market P25/P50/P75):
    Company > P75  → ++ Significantly Above
    Company > P50  → + Somewhat Above
    Company = P50  → = Broadly Aligned
    Company ≥ P25  → - Somewhat Below
    Company < P25  → -- Significantly Below

Value type validation:
    Rejects non-numeric values for percentile scoring.
    Flags value_type mismatches for review.

Parent-child dependencies:
    Read from catalog (dependencies field) instead of hardcoded dict.
"""

from __future__ import annotations

import logging
import re

from src.models import DatapointEntry, ReportRow

logger = logging.getLogger(__name__)

# --- Prevalence extraction ---

_PCT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%")

# Value types that are numeric-compatible for percentile scoring
NUMERIC_VALUE_TYPES = {"percentage", "amount", "number", "days", "weeks", "months", "age", "salary_multiple", "duration"}

# Pattern detecting market-language accidentally placed in company_provision
# e.g. "53.3% of peers offer benefit", "24.2% of peers..."
_MARKET_IN_COMPANY_PATTERN = re.compile(
    r"\d+(?:\.\d+)?%\s+of\s+(?:peers|companies|organizations|market|employers)\b",
    re.IGNORECASE,
)

_COMPOUND_VALUE_PATTERN = re.compile(r"(?:<br>|::|(?:^|\s)[•])", re.IGNORECASE)
_QUALITATIVE_VALUE_PATTERN = re.compile(
    r"\b(?:no\s+(?:overall\s+)?(?:maximum|cap|limit)|unlimited|not\s+capped|fully\s+covered)\b",
    re.IGNORECASE,
)
_BASIS_PATTERNS: dict[str, re.Pattern[str]] = {
    "annual": re.compile(r"\b(?:annual|annually|per\s+year|yearly)\b", re.IGNORECASE),
    "per_birth": re.compile(r"\b(?:per\s+birth|per\s+delivery|per\s+pregnancy|per\s+confinement)\b", re.IGNORECASE),
    "per_visit": re.compile(r"\b(?:per\s+visit|per\s+consultation)\b", re.IGNORECASE),
    "per_day": re.compile(r"\b(?:per\s+day|daily)\b", re.IGNORECASE),
    "lifetime": re.compile(r"\b(?:lifetime|whole\s+life)\b", re.IGNORECASE),
    "monthly": re.compile(r"\b(?:monthly|per\s+month)\b", re.IGNORECASE),
}


def extract_prevalence_pct(market_practice: str) -> tuple[float | None, bool]:
    """Extract the prevalence percentage and its polarity from market_practice.

    Returns (percentage, is_yes_prevalence):
        - is_yes_prevalence=True means the % represents "Yes" adoption
        - is_yes_prevalence=False means the % represents "No" adoption

    When market says "No (76.1%)", that means 76.1% say No.
    We convert to Yes prevalence: 100 - 76.1 = 23.9%.

    Examples:
        "Yes (98.2%)" → (98.2, True)
        "No (76.1%)" → (76.1, False)
        "Not Provided" → (None, True)
        "5.6%" → (5.6, True)   # no prefix defaults to Yes prevalence
    """
    if not market_practice or market_practice in ("N/A", "Not Provided"):
        return None, True
    match = _PCT_PATTERN.search(market_practice)
    if not match:
        return None, True
    pct = float(match.group(1))

    # Determine polarity: does the % refer to "Yes" or "No" respondents?
    stripped = market_practice.strip().lower()
    if stripped.startswith("no"):
        return pct, False
    return pct, True


def _is_company_yes(company_provision: str) -> bool | None:
    """Determine if company provision is affirmative.

    Returns True for "Yes" variants, False for "No" variants, None if unclear.
    "No, ..." (e.g. "No, Forfeit of days not applicable") is negative.
    "No; ..." (e.g. "No; employees must use all leave") is negative.
    """
    val = company_provision.strip().lower()
    if val in ("n/a", "not provided"):
        return None
    if val.startswith("yes") or val.startswith("above statutory"):
        return True
    if val == "no" or val == "none" or val == "0":
        return False
    # "No" followed by any non-alphanumeric separator (comma, semicolon, space, colon, dash)
    if val.startswith("no") and len(val) > 2 and not val[2].isalnum():
        return False
    # If it's a substantive value (not empty, not "no"), treat as "yes"
    if val and val not in ("no", "none", "n/a", "not provided", "0"):
        return True
    return None


def _extract_numeric(value: str) -> float | None:
    """Extract a numeric value from a string for percentile comparison.

    Returns None for range values (e.g. "22-30 days") since scoring would be
    ambiguous without knowing whether to use min, max, or median.

    Examples:
        "1,500" → 1500.0
        "36x annual salary" → 36.0
        "100%" → 100.0
        "50,000" → 50000.0
        "26 weeks" → 26.0
        "22-30 days" → None  (range — cannot score deterministically)
    """
    if not value or value in ("N/A", "Not Provided"):
        return None
    # Reject range values (e.g. "22-30", "22–30") — ambiguous for scoring
    if re.search(r"\d+\s*[-–]\s*\d+", value):
        return None
    # Remove leading currency codes/symbols and thousands separators.
    # Examples: S$5,000, SGD 5,000, HK$5,000, HKD 5,000.
    cleaned = re.sub(
        r"^\s*(?:[A-Za-z]{1,3}\s*)?(?:[$£€¥₹]\s*)?",
        "",
        value,
    )
    cleaned = cleaned.replace(",", "")
    # Try to find a leading number (possibly with x suffix for multiples)
    match = re.match(r"([\d,]+(?:\.\d+)?)", cleaned)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def _extract_percentile_values(market_practice: str) -> dict[str, float | None]:
    """Extract P25, P50, P75 from market_practice string.

    Examples:
        "P50=10%" → {p50: 10.0}
        "100% (P75)" → {p50: 100.0}  (assumes the value is P50 if just one number)
        "4x annual salary (P50)" → {p50: 4.0}
        "70% (P50)" → {p50: 70.0}
    """
    result: dict[str, float | None] = {"p25": None, "p50": None, "p75": None}
    if not market_practice or market_practice in ("N/A", "Not Provided"):
        return result

    # Look for all explicit PXX=X patterns (extract together, never return early)
    p25_match = re.search(r"P25\s*=?\s*([\d,.]+)", market_practice)
    p50_match = re.search(r"P50\s*=?\s*([\d,.]+)", market_practice)
    p75_match = re.search(r"P75\s*=?\s*([\d,.]+)", market_practice)

    if p25_match:
        _val = p25_match.group(1).replace(",", "").strip(".")
        if _val:
            result["p25"] = float(_val)
    if p50_match:
        _val = p50_match.group(1).replace(",", "").strip(".")
        if _val:
            result["p50"] = float(_val)
    if p75_match:
        _val = p75_match.group(1).replace(",", "").strip(".")
        if _val:
            result["p75"] = float(_val)

    # If any explicit PXX= pattern matched, return the combined result
    if any(v is not None for v in result.values()):
        return result

    # If "(P50)" or "(P75)" or "(P25)" appears, extract the leading number
    if "(P50)" in market_practice:
        num = _extract_numeric(market_practice.split("(P50)")[0])
        if num is not None:
            result["p50"] = num
    elif "(P75)" in market_practice:
        num = _extract_numeric(market_practice.split("(P75)")[0])
        if num is not None:
            result["p75"] = num
    elif "(P25)" in market_practice:
        num = _extract_numeric(market_practice.split("(P25)")[0])
        if num is not None:
            result["p25"] = num

    # Fallback: if no explicit percentile label, treat leading number as P50
    if result["p50"] is None and result["p75"] is None:
        num = _extract_numeric(market_practice)
        if num is not None:
            result["p50"] = num

    return result


def compute_prevalence_alignment(
    company_provision: str, market_practice: str, dp: DatapointEntry | None = None
) -> tuple[str, str | None]:
    """Compute alignment for Prevalence logic.

    Handles both "Yes (X%)" and "No (X%)" market polarity.
    Uses alignment.basis from catalog when available:
      - yes_no_prevalence: standard Yes/No comparison
      - selected_option_prevalence: company selected a category, compare to that option's prevalence
      - multi_select_prevalence: multiple options, not scorable → review

    Returns (alignment_string, error_or_None).
    """
    # Check alignment basis
    basis = dp.alignment.basis if dp else "yes_no_prevalence"

    if basis == "not_scored":
        return "N/A", None

    if basis == "multi_select_prevalence":
        # Cannot deterministically score multi-select; flag for review
        return "N/A", "Multi-select prevalence cannot be deterministically scored"

    is_yes = _is_company_yes(company_provision)
    raw_pct, is_yes_prevalence = extract_prevalence_pct(market_practice)

    if is_yes is None:
        return "N/A", None
    if raw_pct is None:
        return "N/A", None

    # For selected_option_prevalence, the market % IS the option's prevalence directly
    if basis == "selected_option_prevalence":
        # The raw_pct represents how many companies selected this option
        yes_pct = raw_pct
        display_pct = raw_pct
    else:
        # yes_no_prevalence: convert to "Yes prevalence"
        # Check catalog-level inversion (e.g. "Fully employer-paid 77%" means 77% say "No" to contribution)
        # When inverted: "No" is the beneficial answer. We flip company and compute beneficial_pct.
        catalog_inverted = dp.alignment.market_prevalence_inverted if dp else False
        if catalog_inverted:
            # Flip company interpretation: "No" → has beneficial answer, "Yes" → against market
            is_yes = not is_yes
            # Calculate beneficial prevalence (% of market with the "No"/beneficial answer)
            # "Yes (23.8%)" → 23.8% say Yes → beneficial = 100-23.8 = 76.2%
            # "Fully employer-paid (77%)" → 77% ARE beneficial → beneficial = 77%
            # "No (77%)" → 77% say No (beneficial) → beneficial = 77%
            stripped_mp = market_practice.strip().lower()
            if stripped_mp.startswith("yes"):
                # Explicit "Yes (X%)" → X% say Yes (non-beneficial), flip to beneficial
                yes_pct = 100.0 - raw_pct
            else:
                # "No (X%)" or non-prefixed text → X% represents the beneficial answer
                yes_pct = raw_pct
        else:
            if is_yes_prevalence:
                yes_pct = raw_pct
            else:
                # Market says "No (X%)" meaning X% don't offer it → (100-X)% do offer it
                yes_pct = 100.0 - raw_pct
        display_pct = raw_pct  # Show original % in output

    if is_yes:
        if yes_pct < 25.0:
            return f"++ Significantly Above ({display_pct}%)", None
        elif yes_pct < 50.0:
            return f"+ Somewhat Above ({display_pct}%)", None
        else:
            return f"= Broadly Aligned ({display_pct}%)", None
    else:
        if yes_pct < 25.0:
            return f"= Broadly Aligned ({display_pct}%)", None
        elif yes_pct < 50.0:
            return f"- Somewhat Below ({display_pct}%)", None
        else:
            return f"-- Significantly Below ({display_pct}%)", None


def compute_percentile_alignment(
    company_provision: str, market_practice: str
) -> tuple[str, str | None]:
    """Compute alignment for 50th Percentile logic.

    Returns (alignment_string, error_or_None).
    """
    company_num = _extract_numeric(company_provision)
    pvals = _extract_percentile_values(market_practice)

    if company_num is None:
        return "N/A", None

    p50 = pvals.get("p50")
    p25 = pvals.get("p25")
    p75 = pvals.get("p75")

    if p50 is None and p75 is None and p25 is None:
        return "N/A", None

    # If we have P50
    if p50 is not None:
        if p75 is not None and company_num > p75:
            return "++ Significantly Above", None
        elif company_num > p50:
            if p75 is not None:
                return "+ Somewhat Above", None
            else:
                return "++ Significantly Above", None
        elif company_num == p50:
            return "= Broadly Aligned", None
        elif p25 is not None and company_num >= p25:
            return "- Somewhat Below", None
        elif company_num < p50:
            if p25 is not None:
                return "-- Significantly Below", None
            else:
                return "-- Significantly Below", None

    return "N/A", "Could not compute percentile alignment"


def _is_straightforward_percentile_comparison(
    company_provision: str,
    market_practice: str,
) -> bool:
    """Return True only when deterministic scalar comparison is defensible."""
    if _QUALITATIVE_VALUE_PATTERN.search(company_provision):
        return False
    if _COMPOUND_VALUE_PATTERN.search(company_provision) or _COMPOUND_VALUE_PATTERN.search(market_practice):
        return False

    company_bases = {
        name for name, pattern in _BASIS_PATTERNS.items() if pattern.search(company_provision)
    }
    market_bases = {
        name for name, pattern in _BASIS_PATTERNS.items() if pattern.search(market_practice)
    }
    if company_bases and market_bases and company_bases.isdisjoint(market_bases):
        return False

    return _extract_numeric(company_provision) is not None and any(
        value is not None for value in _extract_percentile_values(market_practice).values()
    )


def _validate_value_type(company_provision: str, dp: DatapointEntry) -> list[str]:
    """Validate company_provision matches expected value_type.

    Returns list of validation errors (empty if valid).
    """
    errors: list[str] = []
    val = company_provision.strip()

    if val in ("N/A", "Not Provided", ""):
        return errors  # Always acceptable

    vtype = dp.value_type

    if vtype == "yes_no":
        if val.lower() not in ("yes", "no", "above statutory"):
            # Allow substantive values as implicit "yes" but flag for review
            if not val.lower().startswith("yes") and not val.lower().startswith("no"):
                errors.append(f"Expected yes_no but got '{val[:50]}' — treating as implicit yes")

    elif vtype in NUMERIC_VALUE_TYPES:
        num = _extract_numeric(val)
        if num is None:
            errors.append(f"Expected numeric ({vtype}) but value '{val[:50]}' is not parseable")

    return errors


def apply_deterministic_alignment(
    rows: list[ReportRow],
    catalog: list[DatapointEntry],
) -> list[ReportRow]:
    """Override LLM alignment with deterministic scoring.

    Enhanced logic:
    1. Look up catalog entry for alignment rules (basis, positive_option)
    2. Validate value_type compliance
    3. Read parent-child dependencies from catalog
    4. Compute deterministic alignment
    5. Compare with LLM alignment; log mismatches
    6. Set alignment_source and validation_status
    """
    catalog_lookup = {dp.comparison_key: dp for dp in catalog}

    # Build parent provision lookup for dependency validation
    row_lookup: dict[str, ReportRow] = {row.comparison_key: row for row in rows}

    # Build child→parent index from catalog dependencies
    child_parent_map: dict[str, DatapointEntry] = {}
    for dp in catalog:
        if dp.dependencies:
            child_parent_map[dp.comparison_key] = dp

    for row in rows:
        dp = catalog_lookup.get(row.comparison_key)
        if not dp:
            row.alignment_source = "llm"
            row.validation_status = "unmatched"
            row.customer_safe = False
            row.review_reason_code = "NO_CATALOG_ENTRY"
            row.validation_errors.append("No catalog entry found")
            continue

        # Step 1: Validate value_type
        type_errors = _validate_value_type(row.company_provision, dp)
        row.validation_errors.extend(type_errors)

        # Step 1b: Detect market-language in company_provision
        # e.g. "53.3% of peers offer benefit" is a market value, not a company value
        if _MARKET_IN_COMPANY_PATTERN.search(row.company_provision):
            row.company_provision = "Not Provided"
            row.market_alignment = "N/A"
            row.alignment_source = "deterministic"
            row.validation_errors.append(
                "Market-language detected in company_provision — reset to Not Provided"
            )
            row.validation_status = "review"
            row.customer_safe = False
            row.review_reason_code = "MARKET_VALUE_IN_COMPANY_FIELD"
            continue

        # Step 2: Check parent-child dependency (from catalog)
        is_child_of_absent_parent = False
        if dp.dependencies:
            parent_row = row_lookup.get(dp.dependencies.parent_key)
            if parent_row:
                parent_val = parent_row.company_provision.strip().lower()
                parent_is_absent = parent_val in ("no", "none", "0", "not provided", "n/a", "")
                if parent_is_absent and row.company_provision not in ("N/A", "Not Provided", ""):
                    row.validation_errors.append(
                        f"Parent {dp.dependencies.parent_key}='{parent_row.company_provision}' "
                        f"but child has value '{row.company_provision}'"
                    )
                    is_child_of_absent_parent = True
            else:
                # Parent row missing entirely
                row.validation_errors.append(
                    f"Parent row {dp.dependencies.parent_key} not found in output"
                )

        # Step 3: Handle dual-blank N/A (output_rules.dual_blank_outputs_na)
        if (
            row.company_provision in ("N/A", "Not Provided", "")
            and row.market_practice in ("N/A", "Not Provided", "")
        ):
            row.market_alignment = "N/A"
            row.alignment_source = "deterministic"
            row.validation_status = "passed"
            continue

        # Step 4: Compute deterministic alignment using catalog rules
        llm_alignment = row.market_alignment
        basis = dp.alignment.basis

        if basis == "not_scored":
            row.market_alignment = "N/A"
            row.alignment_source = "deterministic"
            row.validation_status = "passed"
            continue

        if dp.alignment.logic == "Prevalence":
            # Check if value_type is numeric but alignment says prevalence (misconfig check)
            if dp.value_type in NUMERIC_VALUE_TYPES and basis == "yes_no_prevalence":
                row.validation_errors.append(
                    f"value_type={dp.value_type} but alignment.basis=yes_no_prevalence — possible misconfiguration"
                )

            det_alignment, err = compute_prevalence_alignment(
                row.company_provision, row.market_practice, dp
            )
        elif dp.alignment.logic == "50th Percentile":
            if not _is_straightforward_percentile_comparison(
                row.company_provision, row.market_practice
            ):
                # Compound, qualitative, or basis-incompatible values require a
                # holistic judgment. Preserve the model alignment without
                # treating a valid qualitative provision as a numeric failure.
                row.validation_errors = [
                    error for error in row.validation_errors
                    if not error.startswith("Expected numeric")
                ]
                row.alignment_source = "llm"
                if row.market_alignment in ("", "N/A", "Not Provided"):
                    row.validation_status = "review"
                    row.customer_safe = False
                    row.review_reason_code = "HOLISTIC_ALIGNMENT_REQUIRED"
                    row.validation_errors.append(
                        "Compound, qualitative, or non-equivalent measures require "
                        "a supported holistic alignment"
                    )
                else:
                    row.validation_status = "passed"
                    row.customer_safe = True
                    row.review_reason_code = None
                continue

            det_alignment, err = compute_percentile_alignment(
                row.company_provision, row.market_practice
            )
        else:
            det_alignment = llm_alignment
            err = None
            row.alignment_source = "llm"
            row.validation_status = "passed"
            continue

        if err:
            row.validation_errors.append(err)

        if det_alignment == "N/A" and llm_alignment not in ("N/A", "Not Provided"):
            # Deterministic couldn't compute but LLM had a value — keep LLM with warning
            row.alignment_source = "llm"
            row.validation_status = "review"
            row.customer_safe = False
            row.review_reason_code = "DETERMINISTIC_CANNOT_COMPUTE"
            row.validation_errors.append(
                f"Deterministic returned N/A but LLM had '{llm_alignment}'"
            )
        else:
            # Compare LLM vs deterministic
            llm_prefix = llm_alignment.split(" ")[0] if llm_alignment else ""
            det_prefix = det_alignment.split(" ")[0] if det_alignment else ""
            if llm_prefix != det_prefix and llm_alignment not in ("N/A", "Not Provided"):
                logger.warning(
                    "Alignment mismatch for %s: LLM='%s' vs Deterministic='%s'",
                    row.comparison_key,
                    llm_alignment,
                    det_alignment,
                )
                row.validation_errors.append(
                    f"LLM alignment '{llm_alignment}' overridden by deterministic '{det_alignment}'"
                )

            row.market_alignment = det_alignment
            row.alignment_source = "deterministic"
            row.validation_status = "passed" if not row.validation_errors else "corrected"

        # Flag parent-child issue
        if is_child_of_absent_parent:
            row.validation_status = "review"
            row.customer_safe = False
            row.review_reason_code = "PARENT_CHILD_CONTRADICTION"

    return rows


def deduplicate_rows(rows: list[ReportRow]) -> list[ReportRow]:
    """Remove duplicate comparison_keys, keeping the first occurrence."""
    seen: set[str] = set()
    deduped: list[ReportRow] = []
    for row in rows:
        if row.comparison_key in seen:
            logger.warning("Duplicate row removed: %s", row.comparison_key)
            continue
        seen.add(row.comparison_key)
        deduped.append(row)
    return deduped


def enforce_parent_child_na(
    rows: list[ReportRow],
    catalog: list[DatapointEntry],
) -> list[ReportRow]:
    """Enforce parent-child N/A: if parent is absent, force child to N/A.

    Uses dependencies from catalog rather than hardcoded map.
    """
    row_lookup = {r.comparison_key: r for r in rows}
    catalog_lookup = {dp.comparison_key: dp for dp in catalog}

    for row in rows:
        dp = catalog_lookup.get(row.comparison_key)
        if not dp or not dp.dependencies:
            continue

        parent_row = row_lookup.get(dp.dependencies.parent_key)
        if not parent_row:
            continue

        parent_val = parent_row.company_provision.strip().lower()
        parent_is_absent = parent_val in ("no", "none", "0", "not provided", "n/a", "")

        if parent_is_absent:
            if row.company_provision not in ("N/A", "Not Provided", ""):
                # Parent absent but child has a value — flag for review but don't override
                # (may be a legitimate exception in the source data)
                pass
            elif row.company_provision in ("Not Provided", ""):
                # Force to N/A since parent benefit doesn't exist
                row.company_provision = "N/A"
                if row.market_practice not in ("N/A",):
                    row.market_practice = row.market_practice  # Keep market for context
                row.market_alignment = "N/A"
                row.alignment_source = "deterministic"

    return rows


def fill_missing_rows(
    rows: list[ReportRow],
    catalog: list[DatapointEntry],
) -> list[ReportRow]:
    """Ensure every catalog datapoint has a row in the output.

    Missing datapoints get a placeholder row. If the missing datapoint has a
    dependency on a parent that is absent, it's filled as N/A.
    """
    existing_keys = {r.comparison_key for r in rows}
    row_lookup = {r.comparison_key: r for r in rows}

    for dp in catalog:
        if dp.comparison_key not in existing_keys:
            # Check if this is a child of an absent parent
            is_na = False
            if dp.dependencies:
                parent_row = row_lookup.get(dp.dependencies.parent_key)
                if parent_row:
                    parent_val = parent_row.company_provision.strip().lower()
                    if parent_val in ("no", "none", "0", "not provided", "n/a", ""):
                        is_na = True

            if is_na:
                new_row = ReportRow(
                    comparison_key=dp.comparison_key,
                    pretty_name=dp.pretty_name,
                    company_provision="N/A",
                    market_practice="N/A",
                    market_alignment="N/A",
                    alignment_source="deterministic",
                    validation_status="passed",
                    validation_errors=["Parent benefit absent — child set to N/A"],
                )
            else:
                new_row = ReportRow(
                    comparison_key=dp.comparison_key,
                    pretty_name=dp.pretty_name,
                    company_provision="Not Provided",
                    market_practice="Not Provided",
                    market_alignment="N/A",
                    alignment_source="deterministic",
                    validation_status="missing",
                    validation_errors=["Not returned by LLM — added as placeholder"],
                )

            rows.append(new_row)
            row_lookup[dp.comparison_key] = new_row

    return rows


# --- Output Format Validation (Step 8) ---

_LITERAL_NEWLINE_PATTERN = re.compile(r"\\n|\\r|\r\n|\r|\n")

# plan attribution pattern — deterministic redaction (NFR-7: never in output)
# Matches: *(Plans: 01 Healthcare)*, *(Plans: 02 Risk)*  etc.
_PLAN_ATTRIBUTION = re.compile(r"\s*\*\(Plans?:\s*[^)]+\)\*")

# Ambiguous plan-name patterns — flagged for review only
# Requires mandatory whitespace between "plan"/"option" and the letter/digit
# to avoid false positives on words like "plans", "planning", "options"
_PLAN_NAME_PATTERNS = re.compile(
    r"\b(plan\s+[A-Z]\b|option\s+[A-Z]\b|tier\s+\d|gold\s+plan|silver\s+plan|bronze\s+plan|platinum\s+plan)\b",
    re.IGNORECASE,
)


def validate_output_format(
    rows: list[ReportRow],
    catalog: list[DatapointEntry],
) -> list[ReportRow]:
    """Validate output format rules from catalog per-datapoint output_rules.

    Checks:
    - no_literal_line_breaks: flags values containing literal newlines
    - suppress_plan_names: flags values that leak plan tier names
    """
    catalog_lookup = {dp.comparison_key: dp for dp in catalog}

    for row in rows:
        dp = catalog_lookup.get(row.comparison_key)
        if not dp:
            continue

        rules = dp.output_rules

        # Check literal line breaks in company_provision and market_practice
        if rules.no_literal_line_breaks:
            for field_name, field_val in [
                ("company_provision", row.company_provision),
                ("market_practice", row.market_practice),
            ]:
                if _LITERAL_NEWLINE_PATTERN.search(field_val):
                    # Auto-fix: replace newlines with semicolons
                    cleaned = _LITERAL_NEWLINE_PATTERN.sub("; ", field_val).strip("; ")
                    if field_name == "company_provision":
                        row.company_provision = cleaned
                    else:
                        row.market_practice = cleaned
                    row.validation_errors.append(
                        f"Literal line break in {field_name} — auto-cleaned"
                    )
                    if row.validation_status == "passed":
                        row.validation_status = "corrected"

        # Check plan name leakage
        if rules.suppress_plan_names:
            # Step A: Deterministic redaction — plan attribution patterns (NFR-7)
            for field_name in ("company_provision", "market_practice"):
                field_val = getattr(row, field_name)
                if _PLAN_ATTRIBUTION.search(field_val):
                    cleaned = _PLAN_ATTRIBUTION.sub("", field_val).strip()
                    setattr(row, field_name, cleaned)
                    row.validation_errors.append(
                        f"Plan attribution redacted from {field_name}"
                    )
                    if row.validation_status == "passed":
                        row.validation_status = "corrected"

            # Step B: Ambiguous plan names — flag for review only
            for field_name, field_val in [
                ("company_provision", row.company_provision),
                ("market_practice", row.market_practice),
            ]:
                match = _PLAN_NAME_PATTERNS.search(field_val)
                if match:
                    row.validation_errors.append(
                        f"Possible plan name '{match.group()}' in {field_name}"
                    )
                    if row.validation_status == "passed":
                        row.validation_status = "review"
                        row.customer_safe = False
                        row.review_reason_code = "AMBIGUOUS_PLAN_NAME"

    # Final normalization: "Not Provided" → "N/A" in market_alignment
    # Valid output alignments are: ++ / + / = / - / -- / N/A
    for row in rows:
        if row.market_alignment.strip().lower() in ("not provided", "not available", "n/a"):
            row.market_alignment = "N/A"

    return rows
