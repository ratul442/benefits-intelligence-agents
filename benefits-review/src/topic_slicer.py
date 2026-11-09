"""Slice Company and Market payloads by benefit topic using markdown headings."""

from __future__ import annotations

import re

from src.models import DatapointEntry, TopicSlice

MAX_DATAPOINTS_PER_BATCH = 15

# Canonical topic names used for matching
TOPICS = [
    "Retirement",
    "Healthcare",
    "Wellbeing",
    "Risk Benefits",
    "Business Travel Insurance",
    "Time Off",
    "Perquisites",
    "Benefits Flexibility and Choice",
    "Meal Benefits",
]

# Mapping of alternate names → canonical topic name
_ALIASES: dict[str, str] = {
    "benefits flexibility": "Benefits Flexibility and Choice",
    "benefits flexibility and choice": "Benefits Flexibility and Choice",
    "meal benefits": "Meal Benefits",
    "meal": "Meal Benefits",
    "risk": "Risk Benefits",
    "risk benefits": "Risk Benefits",
    "business travel": "Business Travel Insurance",
    "business travel insurance": "Business Travel Insurance",
    "time off": "Time Off",
    "perquisites": "Perquisites",
    "retirement": "Retirement",
    "healthcare": "Healthcare",
    "wellbeing": "Wellbeing",
}


def _normalize_topic(raw: str) -> str | None:
    """Map a raw heading to a canonical topic name."""
    key = raw.strip().lower()
    if key in _ALIASES:
        return _ALIASES[key]
    # Try prefix match (e.g. "Healthcare / Dental" → "Healthcare")
    for alias, canonical in _ALIASES.items():
        if key.startswith(alias):
            return canonical
    return None


def _split_markdown_by_h2(md: str) -> dict[str, str]:
    """Split a markdown document into sections by ## headings.

    Returns a dict of {heading_text: section_content}.
    """
    sections: dict[str, str] = {}
    # Match lines starting with ## (but not ###)
    pattern = re.compile(r"^## (.+)$", re.MULTILINE)
    matches = list(pattern.finditer(md))

    for i, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        sections[heading] = md[start:end].strip()

    return sections


def _match_sections_to_topic(
    sections: dict[str, str], topic: str
) -> str:
    """Collect all markdown sections belonging to a canonical topic."""
    parts: list[str] = []
    topic_lower = topic.lower()

    for heading, content in sections.items():
        heading_lower = heading.lower()
        # Direct match or prefix match
        if heading_lower == topic_lower or heading_lower.startswith(topic_lower):
            parts.append(f"## {heading}\n\n{content}")

    return "\n\n".join(parts)


def slice_payloads(
    company_md: str,
    market_md: str,
    catalog: list[DatapointEntry],
) -> list[TopicSlice]:
    """Partition company/market payloads and catalog entries by benefit topic.

    Returns bounded internal batches for each topic that has catalog datapoints.
    Every batch receives the complete Company and Market sections for its topic.
    """
    company_sections = _split_markdown_by_h2(company_md)
    market_sections = _split_markdown_by_h2(market_md)

    # Group catalog entries by topic
    catalog_by_topic: dict[str, list[DatapointEntry]] = {}
    for dp in catalog:
        topic = _normalize_topic(dp.benefit_topic) or dp.benefit_topic
        catalog_by_topic.setdefault(topic, []).append(dp)

    # Build slices
    slices: list[TopicSlice] = []
    for topic in TOPICS:
        datapoints = catalog_by_topic.get(topic, [])
        if not datapoints:
            continue

        company_slice = _match_sections_to_topic(company_sections, topic)
        market_slice = _match_sections_to_topic(market_sections, topic)

        # Skip if no source data at all
        if not company_slice and not market_slice:
            continue

        batch_count = (
            len(datapoints) + MAX_DATAPOINTS_PER_BATCH - 1
        ) // MAX_DATAPOINTS_PER_BATCH
        for batch_index, start in enumerate(
            range(0, len(datapoints), MAX_DATAPOINTS_PER_BATCH),
            start=1,
        ):
            slices.append(
                TopicSlice(
                    topic_name=topic,
                    company_slice=company_slice,
                    market_slice=market_slice,
                    datapoints=datapoints[start:start + MAX_DATAPOINTS_PER_BATCH],
                    batch_index=batch_index,
                    batch_count=batch_count,
                )
            )

    return slices
