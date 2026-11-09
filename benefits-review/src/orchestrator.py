"""Parallel topic orchestration using asyncio.gather with Structured Outputs (v5)."""

from __future__ import annotations

import asyncio
import json
import logging
import time

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


def _is_reasoning_model(model: str) -> bool:
    """Identify GPT-5 reasoning deployments, including named Luna/Terra aliases."""
    normalized = model.strip().lower()
    return normalized.startswith("gpt-5") or any(
        alias in normalized for alias in ("luna", "terra")
    )


def _model_request_parameters(model: str) -> dict:
    """Return only parameters supported by the selected model family."""
    if _is_reasoning_model(model):
        return {"reasoning": {"effort": settings.llm_reasoning_effort}}

    parameters: dict = {"temperature": settings.llm_temperature}
    if settings.llm_top_p is not None:
        parameters["top_p"] = settings.llm_top_p
    return parameters


def _structured_output_keys(raw: str) -> tuple[bool, set[str]]:
    """Return keys present in the raw structured response before row parsing."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return False, set()
    rows = data.get("rows")
    if not isinstance(rows, list):
        return False, set()
    return True, {
        item.get("comparison_key", "").strip()
        for item in rows
        if isinstance(item, dict) and item.get("comparison_key", "").strip()
    }


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
    country: str,
) -> TopicResult:
    """Process one topic batch and retry any keys omitted by the model."""
    start = time.perf_counter()
    topic_name = topic_slice.topic_name

    initial_result = await _call_topic_batch(client, topic_slice, model, country)
    if initial_result.error:
        return initial_result

    expected_keys = {dp.comparison_key for dp in topic_slice.datapoints}
    initial_rows = [
        row for row in initial_result.rows if row.comparison_key in expected_keys
    ]
    returned_keys = {row.comparison_key for row in initial_rows}
    missing_datapoints = [
        dp for dp in topic_slice.datapoints
        if dp.comparison_key not in returned_keys
    ]
    initially_missing_keys = [dp.comparison_key for dp in missing_datapoints]
    model_omitted_keys = (
        sorted(expected_keys - set(initial_result.raw_output_keys))
        if initial_result.structured_output_detected
        else []
    )

    retry_rows: list[ReportRow] = []
    retry_tokens = 0
    retry_error: str | None = None
    retry_parser_dropped_keys: list[str] = []
    if missing_datapoints:
        logger.warning(
            "Model omitted %d/%d keys from %s batch %d/%d; retrying omitted keys",
            len(missing_datapoints),
            len(topic_slice.datapoints),
            topic_name,
            topic_slice.batch_index,
            topic_slice.batch_count,
        )
        retry_slice = topic_slice.model_copy(update={"datapoints": missing_datapoints})
        retry_result = await _call_topic_batch(client, retry_slice, model, country)
        retry_tokens = retry_result.token_usage
        retry_error = retry_result.error
        retry_parser_dropped_keys = retry_result.parser_dropped_keys
        retry_key_set = set(initially_missing_keys)
        retry_rows = [
            row for row in retry_result.rows
            if row.comparison_key in retry_key_set
        ]

    combined_rows = deduplicate_rows(initial_rows + retry_rows)
    combined_keys = {row.comparison_key for row in combined_rows}
    recovered_keys = [
        key for key in initially_missing_keys if key in combined_keys
    ]
    still_missing = [
        key for key in initially_missing_keys if key not in combined_keys
    ]
    if still_missing:
        logger.error(
            "%s batch %d/%d still missing %d keys after retry: %s",
            topic_name,
            topic_slice.batch_index,
            topic_slice.batch_count,
            len(still_missing),
            still_missing,
        )

    return TopicResult(
        topic_name=topic_name,
        rows=combined_rows,
        token_usage=initial_result.token_usage + retry_tokens,
        processing_time_ms=int((time.perf_counter() - start) * 1000),
        error=retry_error,
        initially_missing_keys=initially_missing_keys,
        recovered_keys=recovered_keys,
        model_omitted_keys=model_omitted_keys,
        parser_dropped_keys=sorted(set(
            initial_result.parser_dropped_keys + retry_parser_dropped_keys
        )),
        raw_output_keys=initial_result.raw_output_keys,
        structured_output_detected=initial_result.structured_output_detected,
    )


async def _call_topic_batch(
    client,
    topic_slice: TopicSlice,
    model: str,
    country: str,
) -> TopicResult:
    """Call and parse one bounded topic batch without completeness retries."""
    start = time.perf_counter()
    topic_name = topic_slice.topic_name

    try:
        messages = build_topic_messages(
            topic_name=topic_name,
            company_slice=topic_slice.company_slice,
            market_slice=topic_slice.market_slice,
            datapoints=topic_slice.datapoints,
            country=country,
        )

        # Responses API: system message goes in 'instructions', user messages in 'input'
        system_msg = next((m["content"] for m in messages if m["role"] == "system"), None)
        user_msgs = [m for m in messages if m["role"] != "system"]

        model_parameters = _model_request_parameters(model)

        response = await client.responses.create(
            model=model,
            instructions=system_msg,
            input=user_msgs,  # type: ignore[arg-type]
            max_output_tokens=settings.llm_max_tokens,
            text={"format": _STRUCTURED_OUTPUT_SCHEMA},
            store=True,  # Enable response storage for traceability
            **model_parameters,
        )

        raw_output = response.output_text or ""
        token_usage = (response.usage.total_tokens if response.usage else 0)

        # Parse rows from structured JSON output
        structured_output_detected, raw_output_keys = _structured_output_keys(raw_output)
        rows = _parse_structured_output(raw_output)
        parsed_keys = {row.comparison_key for row in rows}
        parser_dropped_keys = sorted(raw_output_keys - parsed_keys)
        if parser_dropped_keys:
            logger.error(
                "Parser dropped %d keys from %s batch %d/%d: %s",
                len(parser_dropped_keys),
                topic_name,
                topic_slice.batch_index,
                topic_slice.batch_count,
                parser_dropped_keys,
            )

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
            parser_dropped_keys=parser_dropped_keys,
            raw_output_keys=sorted(raw_output_keys),
            structured_output_detected=structured_output_detected,
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

    # Step 2: Process all bounded topic batches in parallel.
    semaphore = asyncio.Semaphore(settings.max_concurrent_topics)

    async def process_bounded(topic_slice: TopicSlice) -> TopicResult:
        async with semaphore:
            return await _process_single_topic(
                client, topic_slice, model_name, request.country
            )

    tasks = [process_bounded(topic_slice) for topic_slice in slices]
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
            process_bounded(slices[i])
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
        per_topic_timing[result.topic_name] = (
            per_topic_timing.get(result.topic_name, 0) + result.processing_time_ms
        )
        if result.error:
            errors.append(f"{result.topic_name}: {result.error}")

    # Step 4: Deduplicate rows (LLM may emit duplicates across topic boundaries)
    all_rows = deduplicate_rows(all_rows)

    returned_keys_before_fill = {row.comparison_key for row in all_rows}
    missing_before_fill = [
        dp.comparison_key for dp in request.datapoints_catalog
        if dp.comparison_key not in returned_keys_before_fill
    ]
    if missing_before_fill:
        logger.error(
            "Aggregation complete with %d catalog keys still missing before placeholder fill: %s",
            len(missing_before_fill),
            missing_before_fill,
        )

    # Step 5: Deterministic alignment override (uses catalog alignment.basis)
    all_rows = apply_deterministic_alignment(all_rows, request.datapoints_catalog)

    # Step 6: Enforce parent-child N/A from catalog dependencies
    all_rows = enforce_parent_child_na(all_rows, request.datapoints_catalog)

    # Step 7: Fill missing rows so all catalog entries are represented
    all_rows = fill_missing_rows(all_rows, request.datapoints_catalog)

    # Step 8: Validate output format rules (line breaks, plan name leakage)
    all_rows = validate_output_format(all_rows, request.datapoints_catalog)

    # Preserve the authoritative catalog's one-to-one source order.
    catalog_order = {
        datapoint.comparison_key: index
        for index, datapoint in enumerate(request.datapoints_catalog)
    }
    all_rows.sort(
        key=lambda row: catalog_order.get(row.comparison_key, len(catalog_order))
    )

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
            topics_processed=len(per_topic_timing),
            model=model_name,
            temperature=(
                None if _is_reasoning_model(model_name)
                else settings.llm_temperature
            ),
            reasoning_effort=(
                settings.llm_reasoning_effort
                if _is_reasoning_model(model_name) else None
            ),
            per_topic_timing=per_topic_timing,
            batches_processed=len(results),
            initially_omitted_datapoints=sum(
                len(result.initially_missing_keys) for result in results
            ),
            recovered_by_retry=sum(len(result.recovered_keys) for result in results),
            model_omitted_datapoints=sum(
                len(result.model_omitted_keys) for result in results
            ),
            parser_dropped_datapoints=sum(
                len(result.parser_dropped_keys) for result in results
            ),
            missing_before_placeholder_fill=len(missing_before_fill),
            agent_version=cfg.agent_version,
            container_tag=cfg.container_tag,
            prompt_version=cfg.prompt_version,
            catalog_version=catalog_version,
        ),
        error="; ".join(errors) if errors else None,
    )
