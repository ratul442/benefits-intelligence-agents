"""Parallel topic orchestration using asyncio.gather with Structured Outputs (v5)."""

from __future__ import annotations

import asyncio
import json
import logging
import time

import openai

from src.config import settings
from src.models import (
    DatapointEntry,
    InvocationRequest,
    InvocationResponse,
    ReportData,
    ReportMetadata,
    ReportRow,
    TopicResult,
    TopicSlice,
)
from src.output_parser import count_valid_rows, parse_llm_output
from src.prompt_builder import build_topic_messages
from src.topic_slicer import slice_payloads
from src.validators import validate_rows
from src.alignment import (
    apply_deterministic_alignment,
    deduplicate_rows,
    enforce_parent_child_na,
    fill_missing_rows,
    validate_output_format,
)

# JSON Schema for Structured Outputs — forces model to return valid JSON
_STRUCTURED_OUTPUT_SCHEMA = {
    "type": "json_schema",
    "name": "benefits_review_output",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "comparison_key": {"type": "string"},
                        "pretty_name": {"type": "string"},
                        "company_provision": {"type": "string"},
                        "market_practice": {"type": "string"},
                        "market_alignment": {"type": "string"},
                    },
                    "required": ["comparison_key", "pretty_name", "company_provision", "market_practice", "market_alignment"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["rows"],
        "additionalProperties": False,
    },
}

logger = logging.getLogger(__name__)


def _parse_structured_output(raw: str) -> list[ReportRow]:
    """Parse JSON structured output from the LLM into ReportRow objects.

    Falls back to pipe-delimited parsing if JSON parsing fails (graceful degradation).
    """
    try:
        data = json.loads(raw)
        rows_data = data.get("rows", [])
        rows: list[ReportRow] = []
        for item in rows_data:
            rows.append(
                ReportRow(
                    comparison_key=item.get("comparison_key", "").strip(),
                    pretty_name=item.get("pretty_name", "").strip(),
                    company_provision=item.get("company_provision", "").strip(),
                    market_practice=item.get("market_practice", "").strip(),
                    market_alignment=item.get("market_alignment", "").strip(),
                )
            )
        if rows:
            logger.info("Structured output parsed: %d rows from JSON", len(rows))
            return rows
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        logger.warning("Structured JSON parse failed (%s), falling back to pipe parser", e)

    # Fallback to pipe-delimited parser if structured output isn't valid JSON
    return parse_llm_output(raw)


async def _process_single_topic(
    client,
    topic_slice: TopicSlice,
    model: str,
) -> TopicResult:
    """Process a single benefit topic: build prompt → call LLM → parse output."""
    start = time.perf_counter()
    topic_name = topic_slice.topic_name

    try:
        messages = build_topic_messages(
            topic_name=topic_name,
            company_slice=topic_slice.company_slice,
            market_slice=topic_slice.market_slice,
            datapoints=topic_slice.datapoints,
        )

        # Responses API: system message goes in 'instructions', user messages in 'input'
        system_msg = next((m["content"] for m in messages if m["role"] == "system"), None)
        user_msgs = [m for m in messages if m["role"] != "system"]

        # NOTE: seed is NOT supported by the Responses API (server returns 400).
        # Determinism is achieved via temperature=0 + structured output schema.
        # The llm_seed config field is retained for future API support / audit trail.

        response = await client.responses.create(
            model=model,
            instructions=system_msg,
            input=user_msgs,  # type: ignore[arg-type]
            temperature=settings.llm_temperature,
            top_p=settings.llm_top_p if settings.llm_top_p is not None else openai.NOT_GIVEN,
            max_output_tokens=settings.llm_max_tokens,
            text={"format": _STRUCTURED_OUTPUT_SCHEMA},
            store=True,  # Enable response storage for traceability
        )

        raw_output = response.output_text or ""
        token_usage = (response.usage.total_tokens if response.usage else 0)

        # Parse rows from structured JSON output
        rows = _parse_structured_output(raw_output)

        # Validate
        validation = validate_rows(rows, topic_slice.datapoints)
        if validation.errors:
            logger.warning(
                "Validation errors for topic %s: %s", topic_name, validation.errors
            )
        if validation.warnings:
            logger.info(
                "Validation warnings for topic %s: %s", topic_name, validation.warnings
            )

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return TopicResult(
            topic_name=topic_name,
            rows=rows,
            token_usage=token_usage,
            processing_time_ms=elapsed_ms,
        )

    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.exception("Error processing topic %s", topic_name)
        return TopicResult(
            topic_name=topic_name,
            processing_time_ms=elapsed_ms,
            error=str(exc),
        )


async def run_benefits_review(
    request: InvocationRequest,
    client,
    model: str | None = None,
) -> InvocationResponse:
    """Execute the full Benefits Review pipeline.

    1. Slice payloads by topic
    2. Process all topics in parallel
    3. Aggregate results
    4. Return structured response
    """
    start = time.perf_counter()
    model_name = model or settings.azure_ai_model_deployment_name

    # Step 1: Slice
    slices = slice_payloads(
        company_md=request.company_payload,
        market_md=request.market_payload,
        catalog=request.datapoints_catalog,
    )

    if not slices:
        return InvocationResponse(
            request_id=request.request_id,
            status="error",
            error="No topic slices could be generated from the input data.",
        )

    # Step 2: Process all topics in parallel (maximum speed)
    tasks = [_process_single_topic(client, s, model_name) for s in slices]
    results: list[TopicResult] = await asyncio.gather(*tasks)

    # Step 2b: Auto-retry topics that crashed due to OTel NonRecordingSpan tracing bug.
    # The hosting TracerProvider can't handle 9+ concurrent spans; after the first
    # batch completes, retries succeed because span capacity is freed.
    failed_indices = [
        i for i, r in enumerate(results)
        if r.error and "NonRecordingSpan" in r.error
    ]
    if failed_indices:
        logger.info("Retrying %d topics that hit tracing errors", len(failed_indices))
        retry_tasks = [
            _process_single_topic(client, slices[i], model_name)
            for i in failed_indices
        ]
        retry_results = await asyncio.gather(*retry_tasks)
        for idx, result in zip(failed_indices, retry_results):
            results[idx] = result

    # Step 3: Aggregate
    all_rows: list[ReportRow] = []
    total_tokens = 0
    per_topic_timing: dict[str, int] = {}
    errors: list[str] = []

    for result in results:
        all_rows.extend(result.rows)
        total_tokens += result.token_usage
        per_topic_timing[result.topic_name] = result.processing_time_ms
        if result.error:
            errors.append(f"{result.topic_name}: {result.error}")

    # Step 4: Deduplicate rows (LLM may emit duplicates across topic boundaries)
    all_rows = deduplicate_rows(all_rows)

    # Step 5: Deterministic alignment override (uses catalog alignment.basis)
    all_rows = apply_deterministic_alignment(all_rows, request.datapoints_catalog)

    # Step 6: Enforce parent-child N/A from catalog dependencies
    all_rows = enforce_parent_child_na(all_rows, request.datapoints_catalog)

    # Step 7: Fill missing rows so all catalog entries are represented
    all_rows = fill_missing_rows(all_rows, request.datapoints_catalog)

    # Step 8: Validate output format rules (line breaks, plan name leakage)
    all_rows = validate_output_format(all_rows, request.datapoints_catalog)

    total, completed, na = count_valid_rows(all_rows)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    # Compute enhanced validation summary
    from collections import Counter
    status_counts = Counter(r.validation_status for r in all_rows)
    source_counts = Counter(r.alignment_source for r in all_rows)
    customer_safe_count = sum(1 for r in all_rows if r.customer_safe)
    review_required_count = sum(1 for r in all_rows if not r.customer_safe)
    from src.models import AlignmentSourceBreakdown, ValidationSummary
    v_summary = ValidationSummary(
        total_rows=len(all_rows),
        passed=status_counts.get("passed", 0),
        corrected=status_counts.get("corrected", 0),
        review=status_counts.get("review", 0),
        missing=status_counts.get("missing", 0),
        failed=status_counts.get("unmatched", 0),
        customer_safe_rows=customer_safe_count,
        review_required_rows=review_required_count,
        alignment_source=AlignmentSourceBreakdown(
            deterministic=source_counts.get("deterministic", 0),
            llm=source_counts.get("llm", 0),
        ),
    )

    # Get catalog version if available
    catalog_version = ""
    # Catalog version is loaded at app startup — pass through
    from src.config import settings as cfg
    catalog_version = getattr(cfg, "catalog_version", "")

    status = "completed" if not errors else "partial"

    return InvocationResponse(
        request_id=request.request_id,
        status=status,
        report=ReportData(
            total_datapoints=total,
            rows_returned=len(all_rows),
            completed_datapoints=completed,
            na_datapoints=na,
            validation_summary=v_summary,
            catalog_version=catalog_version,
            rows=all_rows,
        ),
        metadata=ReportMetadata(
            processing_time_ms=elapsed_ms,
            total_tokens=total_tokens,
            topics_processed=len(results),
            model=model_name,
            per_topic_timing=per_topic_timing,
            agent_version=cfg.agent_version,
            container_tag=cfg.container_tag,
            prompt_version=cfg.prompt_version,
            catalog_version=catalog_version,
        ),
        error="; ".join(errors) if errors else None,
    )
