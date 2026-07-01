"""Parse pipe-delimited LLM output into structured ReportRow objects."""

from __future__ import annotations

import re

from src.models import ReportRow

# Pattern matches: | key | pretty | company | market | alignment |<<EOR>>
_ROW_PATTERN = re.compile(
    r"^\|\s*(?P<key>[^|]+?)\s*\|\s*(?P<pretty>[^|]+?)\s*\|\s*(?P<company>[^|]+?)\s*\|\s*(?P<market>[^|]+?)\s*\|\s*(?P<alignment>[^|]+?)\s*\|<<EOR>>",
    re.MULTILINE,
)


def parse_llm_output(raw: str) -> list[ReportRow]:
    """Parse the pipe-delimited LLM response into structured rows.

    Tolerates leading/trailing whitespace, blank lines, and minor formatting
    deviations. Silently skips lines that don't match the expected format.
    """
    rows: list[ReportRow] = []

    for match in _ROW_PATTERN.finditer(raw):
        rows.append(
            ReportRow(
                comparison_key=match.group("key").strip(),
                pretty_name=match.group("pretty").strip(),
                company_provision=match.group("company").strip(),
                market_practice=match.group("market").strip(),
                market_alignment=match.group("alignment").strip(),
            )
        )

    return rows


def count_valid_rows(rows: list[ReportRow]) -> tuple[int, int, int]:
    """Return (total, completed, na) counts."""
    total = len(rows)
    na = sum(1 for r in rows if r.market_alignment.upper() == "N/A")
    completed = total - na
    return total, completed, na
