"""Evidence-backed semantic completeness audit for extracted report rows."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from src.models import ReportRow, TopicSlice


_AUDIT_SCHEMA = {
    "type": "json_schema",
    "name": "benefits_review_semantic_audit",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "audits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "comparison_key": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["complete", "corrected", "needs_review"],
                        },
                        "company_provision": {"type": "string"},
                        "market_practice": {"type": "string"},
                        "missing_facts": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "company_evidence_quotes": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "market_evidence_quotes": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": [
                        "comparison_key",
                        "status",
                        "company_provision",
                        "market_practice",
                        "missing_facts",
                        "company_evidence_quotes",
                        "market_evidence_quotes",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["audits"],
        "additionalProperties": False,
    },
}

_AUDIT_INSTRUCTIONS = """You verify factual completeness of benefits-review extraction rows.
For every supplied datapoint, compare the initial values with its original prompt and the complete Company and Market topic evidence.
Check additional comments, narrative text, conditional denominators, every material measure, and shared limits that apply to individual service rows.
Use status complete when the row is already complete. Use corrected only when the supplied evidence explicitly supports a corrected value. Use needs_review when evidence is ambiguous.
For every changed Company or Market value, provide one or more exact verbatim evidence quotations from the corresponding supplied evidence. Do not infer, calculate, use outside knowledge, or produce alignment.
"""


@dataclass
class SemanticAuditResult:
    rows: list[ReportRow]
    token_usage: int = 0
    processing_time_ms: int = 0
    audited_rows: int = 0
    incomplete_rows: int = 0
    recovered_facts: int = 0
    unsupported_corrections: int = 0
    review_required: int = 0
    error: str | None = None


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _quotes_supported(quotes: list[str], evidence: str) -> bool:
    normalized_evidence = _normalized_text(evidence)
    return bool(quotes) and all(
        _normalized_text(quote) in normalized_evidence
        for quote in quotes
        if _normalized_text(quote)
    ) and all(_normalized_text(quote) for quote in quotes)


def apply_semantic_audits(
    rows: list[ReportRow],
    audits: list[dict],
    company_evidence: str,
    market_evidence: str,
) -> SemanticAuditResult:
    """Apply only corrections supported by verbatim quotations in source evidence."""
    rows_by_key = {row.comparison_key: row.model_copy(deep=True) for row in rows}
    incomplete = recovered = unsupported = review_required = 0

    for audit in audits:
        key = str(audit.get("comparison_key", "")).strip()
        row = rows_by_key.get(key)
        if row is None:
            continue
        status = audit.get("status")
        if status == "complete":
            continue
        incomplete += 1
        if status == "needs_review":
            row.validation_status = "review"
            row.customer_safe = False
            row.review_reason_code = "SEMANTIC_AUDIT_REVIEW"
            row.validation_errors.append("Semantic audit requires human review")
            review_required += 1
            continue

        proposed_company = str(audit.get("company_provision", "")).strip()
        proposed_market = str(audit.get("market_practice", "")).strip()
        company_changed = proposed_company != row.company_provision
        market_changed = proposed_market != row.market_practice
        company_supported = not company_changed or _quotes_supported(
            audit.get("company_evidence_quotes", []), company_evidence
        )
        market_supported = not market_changed or _quotes_supported(
            audit.get("market_evidence_quotes", []), market_evidence
        )

        if not (company_changed or market_changed) or not (
            company_supported and market_supported
        ):
            unsupported += 1
            row.validation_status = "review"
            row.customer_safe = False
            row.review_reason_code = "UNSUPPORTED_SEMANTIC_CORRECTION"
            row.validation_errors.append(
                "Semantic correction rejected because its evidence quotation was not found"
            )
            review_required += 1
            continue

        if company_changed:
            row.company_provision = proposed_company
        if market_changed:
            row.market_practice = proposed_market
        row.validation_status = "corrected"
        row.review_reason_code = None
        row.validation_errors.append("Evidence-backed semantic audit correction applied")
        recovered += len(audit.get("missing_facts", [])) or 1

    return SemanticAuditResult(
        rows=[rows_by_key[row.comparison_key] for row in rows],
        audited_rows=len(rows),
        incomplete_rows=incomplete,
        recovered_facts=recovered,
        unsupported_corrections=unsupported,
        review_required=review_required,
    )


async def audit_topic_rows(
    client,
    topic_slice: TopicSlice,
    rows: list[ReportRow],
    model: str,
    model_parameters: dict,
    max_output_tokens: int,
) -> SemanticAuditResult:
    """Audit a bounded extraction batch and apply quote-backed corrections."""
    started = time.perf_counter()
    datapoints = [
        {
            "comparison_key": item.comparison_key,
            "pretty_name": item.pretty_name,
            "original_prompt": item.company_prompt,
        }
        for item in topic_slice.datapoints
    ]
    payload = {
        "topic": topic_slice.topic_name,
        "company_evidence": topic_slice.company_slice,
        "market_evidence": topic_slice.market_slice,
        "datapoints": datapoints,
        "initial_rows": [row.model_dump(mode="json") for row in rows],
    }
    try:
        response = await client.responses.create(
            model=model,
            instructions=_AUDIT_INSTRUCTIONS,
            input=[{"role": "user", "content": json.dumps(payload, ensure_ascii=True)}],
            max_output_tokens=max_output_tokens,
            text={"format": _AUDIT_SCHEMA},
            store=True,
            **model_parameters,
        )
        raw = json.loads(response.output_text or "{}")
        result = apply_semantic_audits(
            rows,
            raw.get("audits", []),
            topic_slice.company_slice,
            topic_slice.market_slice,
        )
        result.token_usage = response.usage.total_tokens if response.usage else 0
        result.processing_time_ms = int((time.perf_counter() - started) * 1000)
        return result
    except Exception as exc:
        return SemanticAuditResult(
            rows=rows,
            processing_time_ms=int((time.perf_counter() - started) * 1000),
            error=str(exc),
        )
