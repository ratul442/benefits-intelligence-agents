"""Pydantic models for request/response contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field


# --- Catalog Models ---


class MarketMapping(BaseModel):
    """Structured market mapping for a datapoint."""

    question: str = ""
    option: str | None = None
    match_strategy: str = "section_match"  # "exact_option" | "section_match"


class AlignmentRule(BaseModel):
    """Machine-readable alignment configuration."""

    logic: str = "Prevalence"  # "Prevalence" | "50th Percentile"
    basis: str = "yes_no_prevalence"  # "yes_no_prevalence" | "selected_option_prevalence" | "multi_select_prevalence" | "numeric_percentile" | "not_scored"
    positive_option: str | None = "Yes"
    market_prevalence_inverted: bool = False  # When True, the market % represents the NEGATIVE answer (e.g. "Fully employer-paid 77%" means 77% do NOT require employee contribution)


class DependencyRule(BaseModel):
    """Parent-child dependency for conditional datapoints."""

    parent_key: str
    required_parent_values: list[str] = Field(default_factory=lambda: ["Yes"])
    if_not_met: str = "N/A"


class OutputRules(BaseModel):
    """Per-datapoint output constraints."""

    allow_not_provided: bool = True
    dual_blank_outputs_na: bool = True
    suppress_plan_names: bool = True
    no_literal_line_breaks: bool = True


class DatapointEntry(BaseModel):
    """A single datapoint from the Benefits Review Catalog (hardened schema)."""

    comparison_key: str
    pretty_name: str
    benefit_topic: str
    company_prompt: str
    value_type: str = "yes_no"  # yes_no|percentage|amount|number|days|weeks|months|age|salary_multiple|category|multi_select_list|duration|free_text
    alignment: AlignmentRule = Field(default_factory=AlignmentRule)
    format_tag: str = "F4"
    market_mapping: MarketMapping | None = None
    dependencies: DependencyRule | None = None
    output_rules: OutputRules = Field(default_factory=OutputRules)
    source_sort_order: int | None = None
    source_primary_name: str | None = None
    source_country_iso: str | None = None
    source_benefit_type: str | None = None

    # Legacy compat — derived from alignment.logic
    @property
    def alignment_logic(self) -> str:
        return self.alignment.logic


class InvocationRequest(BaseModel):
    """Request payload from BOL backend."""

    request_id: str = Field(default="")
    country: str = Field(default="SGP")
    company_payload: str
    market_payload: str
    datapoints_catalog: list[DatapointEntry]


# --- Internal Models ---


class TopicSlice(BaseModel):
    """Data partition for a single benefit topic."""

    topic_name: str
    company_slice: str
    market_slice: str
    datapoints: list[DatapointEntry]
    batch_index: int = 1
    batch_count: int = 1


# --- Output Models ---


class ReportRow(BaseModel):
    """A single row in the Benefits Review output."""

    comparison_key: str
    pretty_name: str
    company_provision: str
    market_practice: str
    market_alignment: str
    alignment_source: str = "llm"  # "llm" | "deterministic"
    validation_status: str = "passed"  # "passed" | "corrected" | "review" | "missing" | "unmatched"
    customer_safe: bool = True  # False for review/unmatched rows — BOL should suppress or flag
    review_reason_code: str | None = None  # Machine-readable code (e.g., NON_NUMERIC_COMPANY_VALUE)
    validation_errors: list[str] = Field(default_factory=list)


class TopicResult(BaseModel):
    """Result from processing a single topic."""

    topic_name: str
    rows: list[ReportRow] = Field(default_factory=list)
    token_usage: int = 0
    processing_time_ms: int = 0
    error: str | None = None
    initially_missing_keys: list[str] = Field(default_factory=list)
    recovered_keys: list[str] = Field(default_factory=list)
    model_omitted_keys: list[str] = Field(default_factory=list)
    parser_dropped_keys: list[str] = Field(default_factory=list)
    raw_output_keys: list[str] = Field(default_factory=list)
    structured_output_detected: bool = False


class InvocationResponse(BaseModel):
    """Response payload returned to BOL backend."""

    request_id: str
    status: str = "completed"
    report: ReportData | None = None
    metadata: ReportMetadata | None = None
    error: str | None = None


class AlignmentSourceBreakdown(BaseModel):
    """Breakdown of alignment sources."""

    deterministic: int = 0
    llm: int = 0


class ValidationSummary(BaseModel):
    """Counts of rows by validation status."""

    total_rows: int = 0
    passed: int = 0
    corrected: int = 0
    review: int = 0
    missing: int = 0
    failed: int = 0
    customer_safe_rows: int = 0  # passed + corrected + missing (safe to show customers)
    review_required_rows: int = 0  # review + failed (needs SME attention)
    alignment_source: AlignmentSourceBreakdown = Field(default_factory=AlignmentSourceBreakdown)


class ReportData(BaseModel):
    total_datapoints: int = 0
    rows_returned: int = 0
    completed_datapoints: int = 0
    na_datapoints: int = 0
    validation_summary: ValidationSummary = Field(default_factory=ValidationSummary)
    catalog_version: str = ""
    rows: list[ReportRow] = Field(default_factory=list)


class ReportMetadata(BaseModel):
    processing_time_ms: int = 0
    total_tokens: int = 0
    topics_processed: int = 0
    model: str = ""
    temperature: float | None = None
    reasoning_effort: str | None = None
    per_topic_timing: dict[str, int] = Field(default_factory=dict)
    batches_processed: int = 0
    initially_omitted_datapoints: int = 0
    recovered_by_retry: int = 0
    model_omitted_datapoints: int = 0
    parser_dropped_datapoints: int = 0
    missing_before_placeholder_fill: int = 0
    # Deployment traceability
    agent_version: str = ""
    container_tag: str = ""
    prompt_version: str = ""
    catalog_version: str = ""
