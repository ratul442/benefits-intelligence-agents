"""Build LLM messages for per-topic invocations."""

from __future__ import annotations

from pathlib import Path

from src.models import DatapointEntry

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_SYSTEM_PROMPT: str | None = None

_COUNTRY_CONTEXTS = {
    "SGP": (
        "Interpret global datapoints in the Singapore context. Recognize locally "
        "equivalent arrangements and terminology such as CPF, statutory versus "
        "supplementary employer benefits, and SGD-denominated limits. Preserve "
        "the datapoint's intent and remain grounded in the supplied Company and "
        "Market profiles; do not infer a provision merely because it is common "
        "or statutory in Singapore."
    ),
}


def _load_system_prompt() -> str:
    """Load system prompt from file (cached after first read)."""
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = (_PROMPT_DIR / "system_prompt.md").read_text(encoding="utf-8")
    return _SYSTEM_PROMPT


def _format_catalog(datapoints: list[DatapointEntry]) -> str:
    """Format catalog entries as a markdown table for the LLM."""
    lines = [
        "| ComparisonKey | PrettyName | CompanyPrompt | AlignmentLogic | Format |",
        "|---|---|---|---|---|",
    ]
    for dp in datapoints:
        # Escape pipe characters in company_prompt
        prompt_escaped = dp.company_prompt.replace("|", "\\|")
        lines.append(
            f"| {dp.comparison_key} | {dp.pretty_name} | {prompt_escaped} | {dp.alignment_logic} | {dp.format_tag} |"
        )
    return "\n".join(lines)


def _build_country_context(country: str) -> str:
    """Build an agent-level interpretation layer for the requested country."""
    country_code = (country or "").strip().upper()
    if country_code in _COUNTRY_CONTEXTS:
        return _COUNTRY_CONTEXTS[country_code]
    return (
        f"Interpret global datapoints in the supplied {country_code or 'country'} "
        "context. Recognize equivalent local terminology and benefit structures, "
        "but remain grounded in the supplied Company and Market profiles and do "
        "not add provisions from general country knowledge."
    )


def build_topic_messages(
    topic_name: str,
    company_slice: str,
    market_slice: str,
    datapoints: list[DatapointEntry],
    country: str = "SGP",
) -> list[dict[str, str]]:
    """Build chat messages for a single topic invocation.

    Returns a list of {"role": ..., "content": ...} dicts ready for
    the Azure OpenAI chat completions API.
    """
    system_msg = (
        f"{_load_system_prompt()}\n\n"
        f"## COUNTRY CONTEXT\n\n"
        f"Country: {country.strip().upper() or 'Not specified'}\n\n"
        f"{_build_country_context(country)}"
    )

    catalog_text = _format_catalog(datapoints)

    user_msg = (
        f"### INPUTS\n\n"
        f"**TOPIC:** {topic_name}\n\n"
        f"**DATA CATALOG:**\n{catalog_text}\n\n"
        f"**COMPANY SLICE:**\n{company_slice}\n\n"
        f"**INDUSTRY SLICE:**\n{market_slice}"
    )

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]
