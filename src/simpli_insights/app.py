"""FastAPI application."""

from __future__ import annotations

import json as json_module
import re
import uuid
from datetime import datetime
from typing import Any

import litellm
import structlog
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from simpli_core import CostTracker, create_app
from simpli_core.connectors import (
    FieldMapping,
    FileConnector,
    SalesforceConnector,
    apply_mappings,
)
from simpli_core.connectors.mapping import CASE_TO_TICKET

from simpli_insights import __version__
from simpli_insights.settings import settings

cost_tracker = CostTracker()
logger = structlog.get_logger(__name__)

app = create_app(
    title="Simpli Insights",
    version=__version__,
    description="Theme discovery and pattern analysis for customer support cases",
    settings=settings,
    cors_origins=settings.cors_origins,
    cost_tracker=cost_tracker,
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Case(BaseModel):
    id: str = Field(min_length=1, description="Unique case identifier")
    subject: str = Field(min_length=1, description="Case subject line")
    content: str = Field(min_length=1, description="Full case content text")
    category: str | None = Field(default=None, description="Case category or type")
    tags: list[str] = Field(default_factory=list, description="Tags associated with the case")
    created_at: datetime | None = Field(default=None, description="When the case was created")
    resolved: bool | None = Field(default=None, description="Whether the case has been resolved")


# -- Themes --


class ThemesRequest(BaseModel):
    cases: list[Case] = Field(min_length=3, description="Cases to discover themes from (minimum 3)")


class Theme(BaseModel):
    theme_id: str = Field(description="Unique theme identifier")
    name: str = Field(description="Theme name")
    description: str = Field(description="Description of the theme")
    case_ids: list[str] = Field(description="IDs of cases belonging to this theme")
    case_count: int = Field(description="Number of cases in this theme")
    sample_subjects: list[str] = Field(description="Sample subject lines from this theme")


class ThemesResponse(BaseModel):
    audit_id: str = Field(description="Unique identifier for this theme analysis")
    total_cases: int = Field(description="Number of cases analyzed")
    themes: list[Theme] = Field(description="Discovered themes")
    uncategorized_case_ids: list[str] = Field(description="Cases that didn't fit any theme")


# -- Emerging --


class EmergingRequest(BaseModel):
    recent_cases: list[Case] = Field(min_length=1, description="Recent cases to analyze for trends")
    baseline_cases: list[Case] | None = Field(default=None, description="Older cases for comparison baseline")


class EmergingTopic(BaseModel):
    topic: str = Field(description="Emerging topic name")
    case_count: int = Field(description="Number of cases related to this topic")
    growth_rate: float = Field(description="Rate of increase compared to baseline")
    first_seen: str | None = Field(default=None, description="When this topic was first observed")
    case_ids: list[str] = Field(description="IDs of cases related to this topic")


class EmergingResponse(BaseModel):
    audit_id: str = Field(description="Unique identifier for this emerging topics analysis")
    total_recent: int = Field(description="Number of recent cases analyzed")
    total_baseline: int | None = Field(description="Number of baseline cases used for comparison")
    topics: list[EmergingTopic] = Field(description="Detected emerging topics")


# -- Categories --


class CategoriesRequest(BaseModel):
    cases: list[Case] = Field(min_length=3, description="Cases to derive categories from (minimum 3)")
    existing_categories: list[str] | None = Field(default=None, description="Current category names to compare against")


class SuggestedCategory(BaseModel):
    name: str = Field(description="Category name")
    description: str = Field(description="Category description")
    case_count: int = Field(description="Estimated number of cases in this category")
    case_ids: list[str] = Field(description="IDs of cases assigned to this category")
    is_new: bool = Field(description="Whether this is a newly suggested category")


class CategoriesResponse(BaseModel):
    audit_id: str = Field(description="Unique identifier for this category analysis")
    total_cases: int = Field(description="Number of cases analyzed")
    categories: list[SuggestedCategory] = Field(description="Suggested categories")
    unmapped_case_ids: list[str] = Field(description="Cases not assigned to any category")


# -- Distribution --


class DistributionRequest(BaseModel):
    cases: list[Case] = Field(min_length=1, description="Cases to analyze distribution for")


class CategoryDistribution(BaseModel):
    category: str = Field(description="Category name")
    count: int = Field(description="Number of cases in this category")
    percentage: float = Field(description="Percentage of total cases")


class DistributionResponse(BaseModel):
    audit_id: str = Field(description="Unique identifier for this distribution analysis")
    total_cases: int = Field(description="Total number of cases analyzed")
    distribution: list[CategoryDistribution] = Field(description="Distribution of cases across categories")
    uncategorized_count: int = Field(description="Number of cases without a category")


# ---------------------------------------------------------------------------
# Versioned API router
# ---------------------------------------------------------------------------

v1 = APIRouter(prefix="/api/v1")

THEMES_SYSTEM_PROMPT = (
    "You are a support theme analyst. Given a batch of support cases, "
    "discover recurring themes and patterns. "
    "Return JSON with: themes (list of {name, description, frequency, "
    "representative_cases (list of case_ids), severity})."
)

EMERGING_SYSTEM_PROMPT = (
    "You are a trend detector for customer support. Given recent cases with "
    "timestamps, identify emerging or trending topics. "
    "Return JSON with: topics (list of {name, description, growth_rate, "
    "first_seen, case_count, risk_level})."
)

CATEGORIES_SYSTEM_PROMPT = (
    "You are a taxonomy designer for customer support. Given cases, suggest "
    "an optimal category taxonomy. "
    "Return JSON with: categories (list of {name, description, parent (optional), "
    "estimated_percentage})."
)

DISTRIBUTION_SYSTEM_PROMPT = (
    "You are a support distribution analyst. Given cases and existing categories, "
    "analyze how cases distribute across categories. "
    "Return JSON with: distribution (list of {category, count, percentage, trend}), "
    "uncategorized_count (int), recommendations (list of strings)."
)


def _parse_llm_json(raw: str) -> dict:
    """Extract JSON from LLM output, handling code fences and embedded JSON."""
    text = raw.strip()
    # Strip markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    # Find first { ... } block
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        text = brace_match.group(0)
    return json_module.loads(text)


@v1.post("/themes", response_model=ThemesResponse, tags=["themes"], summary="Discover recurring themes from support cases")
async def discover_themes(request: ThemesRequest) -> ThemesResponse:
    """Discover themes from a batch of support cases."""
    audit_id = str(uuid.uuid4())

    cases_text = "\n".join(
        f"- Case {c.id}: {c.subject} — {c.content[:200]}"
        + (f" [tags: {', '.join(c.tags)}]" if c.tags else "")
        for c in request.cases
    )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": THEMES_SYSTEM_PROMPT},
        {"role": "user", "content": cases_text},
    ]

    response = await litellm.acompletion(
        model=settings.litellm_model,
        messages=messages,
        temperature=0.2,
    )
    cost_tracker.record_from_response(settings.litellm_model, response)

    raw = response.choices[0].message.content or ""
    try:
        parsed = _parse_llm_json(raw)
    except (json_module.JSONDecodeError, TypeError):
        logger.warning("themes_parse_error", audit_id=audit_id, raw=raw[:200])
        parsed = {}

    themes: list[Theme] = []
    themed_ids: set[str] = set()
    for t in parsed.get("themes", []):
        rep_cases = t.get("representative_cases", [])
        theme = Theme(
            theme_id=str(uuid.uuid4()),
            name=t.get("name", "unknown"),
            description=t.get("description", ""),
            case_ids=rep_cases,
            case_count=int(t.get("frequency", len(rep_cases))),
            sample_subjects=[],
        )
        themes.append(theme)
        themed_ids.update(rep_cases)

    uncategorized = [c.id for c in request.cases if c.id not in themed_ids]

    logger.info("themes_requested", audit_id=audit_id, total_cases=len(request.cases))
    return ThemesResponse(
        audit_id=audit_id,
        total_cases=len(request.cases),
        themes=themes,
        uncategorized_case_ids=uncategorized,
    )


@v1.post("/emerging", response_model=EmergingResponse, tags=["emerging"], summary="Detect emerging or trending support topics")
async def detect_emerging(request: EmergingRequest) -> EmergingResponse:
    """Detect emerging or trending topics in recent cases."""
    audit_id = str(uuid.uuid4())

    recent_text = "\n".join(
        f"- Case {c.id} ({c.created_at or 'no date'}): {c.subject} — {c.content[:200]}"
        for c in request.recent_cases
    )
    content = f"Recent cases:\n{recent_text}"
    if request.baseline_cases:
        baseline_text = "\n".join(
            f"- Case {c.id} ({c.created_at or 'no date'}): {c.subject}"
            for c in request.baseline_cases
        )
        content += f"\n\nBaseline cases:\n{baseline_text}"

    messages: list[dict[str, str]] = [
        {"role": "system", "content": EMERGING_SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]

    response = await litellm.acompletion(
        model=settings.litellm_model,
        messages=messages,
        temperature=0.2,
    )
    cost_tracker.record_from_response(settings.litellm_model, response)

    raw = response.choices[0].message.content or ""
    try:
        parsed = _parse_llm_json(raw)
    except (json_module.JSONDecodeError, TypeError):
        logger.warning("emerging_parse_error", audit_id=audit_id, raw=raw[:200])
        parsed = {}

    topics: list[EmergingTopic] = []
    for t in parsed.get("topics", []):
        topics.append(
            EmergingTopic(
                topic=t.get("name", "unknown"),
                case_count=int(t.get("case_count", 0)),
                growth_rate=float(t.get("growth_rate", 0.0)),
                first_seen=t.get("first_seen"),
                case_ids=[],
            )
        )

    logger.info(
        "emerging_requested",
        audit_id=audit_id,
        total_recent=len(request.recent_cases),
    )
    return EmergingResponse(
        audit_id=audit_id,
        total_recent=len(request.recent_cases),
        total_baseline=len(request.baseline_cases) if request.baseline_cases else None,
        topics=topics,
    )


@v1.post("/categories", response_model=CategoriesResponse, tags=["categories"], summary="Suggest a category taxonomy from support cases")
async def suggest_categories(request: CategoriesRequest) -> CategoriesResponse:
    """Suggest a category taxonomy from support cases."""
    audit_id = str(uuid.uuid4())

    cases_text = "\n".join(
        f"- Case {c.id}: {c.subject} — {c.content[:200]}"
        for c in request.cases
    )
    content = f"Cases:\n{cases_text}"
    if request.existing_categories:
        content += f"\n\nExisting categories: {', '.join(request.existing_categories)}"

    messages: list[dict[str, str]] = [
        {"role": "system", "content": CATEGORIES_SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]

    response = await litellm.acompletion(
        model=settings.litellm_model,
        messages=messages,
        temperature=0.2,
    )
    cost_tracker.record_from_response(settings.litellm_model, response)

    raw = response.choices[0].message.content or ""
    try:
        parsed = _parse_llm_json(raw)
    except (json_module.JSONDecodeError, TypeError):
        logger.warning("categories_parse_error", audit_id=audit_id, raw=raw[:200])
        parsed = {}

    categories: list[SuggestedCategory] = []
    mapped_ids: set[str] = set()
    existing_set = set(request.existing_categories or [])

    for cat in parsed.get("categories", []):
        name = cat.get("name", "unknown")
        # Estimate case count from percentage
        pct = float(cat.get("estimated_percentage", 0))
        case_count = round(pct / 100 * len(request.cases)) if pct else 0
        categories.append(
            SuggestedCategory(
                name=name,
                description=cat.get("description", ""),
                case_count=case_count,
                case_ids=[],
                is_new=name not in existing_set,
            )
        )

    unmapped = [c.id for c in request.cases if c.id not in mapped_ids]

    logger.info(
        "categories_requested",
        audit_id=audit_id,
        total_cases=len(request.cases),
    )
    return CategoriesResponse(
        audit_id=audit_id,
        total_cases=len(request.cases),
        categories=categories,
        unmapped_case_ids=unmapped,
    )


@v1.post("/distribution", response_model=DistributionResponse, tags=["distribution"], summary="Analyse case distribution across categories")
async def analyse_distribution(request: DistributionRequest) -> DistributionResponse:
    """Analyse distribution of cases across existing categories."""
    audit_id = str(uuid.uuid4())

    cases_text = "\n".join(
        f"- Case {c.id}: {c.subject}"
        + (f" [category: {c.category}]" if c.category else "")
        + f" — {c.content[:200]}"
        for c in request.cases
    )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": DISTRIBUTION_SYSTEM_PROMPT},
        {"role": "user", "content": cases_text},
    ]

    response = await litellm.acompletion(
        model=settings.litellm_model,
        messages=messages,
        temperature=0.2,
    )
    cost_tracker.record_from_response(settings.litellm_model, response)

    raw = response.choices[0].message.content or ""
    try:
        parsed = _parse_llm_json(raw)
    except (json_module.JSONDecodeError, TypeError):
        logger.warning("distribution_parse_error", audit_id=audit_id, raw=raw[:200])
        parsed = {}

    distribution: list[CategoryDistribution] = []
    for d in parsed.get("distribution", []):
        distribution.append(
            CategoryDistribution(
                category=d.get("category", "unknown"),
                count=int(d.get("count", 0)),
                percentage=float(d.get("percentage", 0.0)),
            )
        )

    uncategorized_count = int(parsed.get("uncategorized_count", 0))

    logger.info(
        "distribution_requested",
        audit_id=audit_id,
        total_cases=len(request.cases),
    )
    return DistributionResponse(
        audit_id=audit_id,
        total_cases=len(request.cases),
        distribution=distribution,
        uncategorized_count=uncategorized_count,
    )


app.include_router(v1)


# ---------------------------------------------------------------------------
# Ingest models
# ---------------------------------------------------------------------------


class SalesforceIngestRequest(BaseModel):
    """Request to ingest data from Salesforce."""

    instance_url: str = Field(
        default="", description="Salesforce instance URL (uses server default if empty)"
    )
    client_id: str = Field(
        default="", description="OAuth2 client ID (uses server default if empty)"
    )
    client_secret: str = Field(
        default="", description="OAuth2 client secret (uses server default if empty)"
    )
    soql_where: str = Field(
        default="", description="Optional WHERE clause filter for SOQL query"
    )
    limit: int = Field(default=100, ge=1, le=10000, description="Max records to fetch")
    mappings: list[FieldMapping] | None = Field(
        default=None,
        description="Custom field mappings (uses defaults if not provided)",
    )


class IngestResult(BaseModel):
    """Result of an ingest operation."""

    total: int = Field(description="Total records received")
    processed: int = Field(description="Records successfully processed")
    results: list[dict[str, Any]] = Field(description="Processing results")
    errors: list[dict[str, Any]] = Field(
        default_factory=list, description="Records that failed processing"
    )


# ---------------------------------------------------------------------------
# Ingest routes
# ---------------------------------------------------------------------------


@app.post("/api/v1/ingest", response_model=IngestResult, tags=["ingest"], summary="Ingest cases from a file and discover themes")
async def ingest_file(
    file: UploadFile = File(  # noqa: B008
        ..., description="File to ingest (CSV, JSON, or JSONL)"
    ),
    mappings: str | None = Form(
        default=None, description="JSON array of field mappings"
    ),
) -> IngestResult:
    """Ingest cases from a file upload and discover themes."""
    logger.info("ingest_file", filename=file.filename)

    records = FileConnector.parse(file.file, format=_detect_format(file.filename))

    field_mappings: list[FieldMapping] | None = None
    if mappings:
        field_mappings = [FieldMapping(**m) for m in json_module.loads(mappings)]

    return await _process_records(records, field_mappings, apply_defaults=False)


@app.post("/api/v1/ingest/salesforce", response_model=IngestResult, tags=["ingest"], summary="Pull Salesforce cases and discover themes")
async def ingest_salesforce(request: SalesforceIngestRequest) -> IngestResult:
    """Pull cases from Salesforce and discover themes."""
    instance_url = request.instance_url or settings.salesforce_instance_url
    client_id = request.client_id or settings.salesforce_client_id
    client_secret = request.client_secret or settings.salesforce_client_secret

    if not all([instance_url, client_id, client_secret]):
        return JSONResponse(  # type: ignore[return-value]
            status_code=400,
            content={
                "detail": "Salesforce credentials required"
                " (instance_url, client_id, client_secret)"
            },
        )

    logger.info("ingest_salesforce", instance_url=instance_url, limit=request.limit)

    connector = SalesforceConnector(
        instance_url=instance_url,
        client_id=client_id,
        client_secret=client_secret,
    )
    records = connector.get_cases(where=request.soql_where, limit=request.limit)

    return await _process_records(records, request.mappings)


def _detect_format(filename: str | None) -> str:
    """Detect file format from filename."""
    if not filename:
        return "csv"
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "csv"
    return suffix if suffix in FileConnector.SUPPORTED_FORMATS else "csv"


async def _process_records(
    records: list[dict[str, Any]],
    custom_mappings: list[FieldMapping] | None,
    *,
    apply_defaults: bool = True,
) -> IngestResult:
    """Apply mappings to records and discover themes."""
    if custom_mappings:
        mapped = apply_mappings(records, custom_mappings, preserve_unmapped=settings.preserve_unmapped_fields)
    elif apply_defaults:
        mapped = apply_mappings(records, CASE_TO_TICKET, preserve_unmapped=settings.preserve_unmapped_fields)
    else:
        mapped = records

    errors: list[dict[str, Any]] = []
    cases: list[Case] = []

    for i, record in enumerate(mapped):
        try:
            subject = record.get("subject", record.get("Subject", "Unknown"))
            description = (
                record.get("description")
                or record.get("body")
                or record.get("content")
                or record.get("text")
                or ""
            )
            content = (
                f"Subject: {subject}\n\n{description}".strip()
                if subject and description
                else (description or subject or "")
            )
            cases.append(
                Case(
                    id=record.get("id", f"ingest-{i}"),
                    subject=subject,
                    content=content,
                    category=record.get("category"),
                )
            )
        except Exception as exc:
            errors.append({"index": i, "error": str(exc), "record": record})

    results: list[dict[str, Any]] = []
    if len(cases) >= 3:
        resp = await discover_themes(ThemesRequest(cases=cases))
        results.append(resp.model_dump())
    elif cases:
        # Not enough cases for theme discovery — return individual case data
        results = [c.model_dump() for c in cases]

    return IngestResult(
        total=len(records),
        processed=len(cases),
        results=results,
        errors=errors,
    )
