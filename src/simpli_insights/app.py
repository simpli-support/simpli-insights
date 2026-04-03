"""FastAPI application."""

from __future__ import annotations

import json as json_module
import uuid
from datetime import datetime
from typing import Any

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
    id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    content: str = Field(min_length=1)
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    resolved: bool | None = None


# -- Themes --


class ThemesRequest(BaseModel):
    cases: list[Case] = Field(min_length=3)


class Theme(BaseModel):
    theme_id: str
    name: str
    description: str
    case_ids: list[str]
    case_count: int
    sample_subjects: list[str]


class ThemesResponse(BaseModel):
    audit_id: str
    total_cases: int
    themes: list[Theme]
    uncategorized_case_ids: list[str]


# -- Emerging --


class EmergingRequest(BaseModel):
    recent_cases: list[Case] = Field(min_length=1)
    baseline_cases: list[Case] | None = None


class EmergingTopic(BaseModel):
    topic: str
    case_count: int
    growth_rate: float
    first_seen: str | None = None
    case_ids: list[str]


class EmergingResponse(BaseModel):
    audit_id: str
    total_recent: int
    total_baseline: int | None
    topics: list[EmergingTopic]


# -- Categories --


class CategoriesRequest(BaseModel):
    cases: list[Case] = Field(min_length=3)
    existing_categories: list[str] | None = None


class SuggestedCategory(BaseModel):
    name: str
    description: str
    case_count: int
    case_ids: list[str]
    is_new: bool


class CategoriesResponse(BaseModel):
    audit_id: str
    total_cases: int
    categories: list[SuggestedCategory]
    unmapped_case_ids: list[str]


# -- Distribution --


class DistributionRequest(BaseModel):
    cases: list[Case] = Field(min_length=1)


class CategoryDistribution(BaseModel):
    category: str
    count: int
    percentage: float


class DistributionResponse(BaseModel):
    audit_id: str
    total_cases: int
    distribution: list[CategoryDistribution]
    uncategorized_count: int


# ---------------------------------------------------------------------------
# Versioned API router
# ---------------------------------------------------------------------------

v1 = APIRouter(prefix="/api/v1")


@v1.post("/themes", response_model=ThemesResponse, tags=["themes"])
async def discover_themes(request: ThemesRequest) -> ThemesResponse:
    """Discover themes from a batch of support cases."""
    audit_id = str(uuid.uuid4())
    # TODO: replace stub with real litellm call
    logger.info("themes_requested", audit_id=audit_id, total_cases=len(request.cases))
    return ThemesResponse(
        audit_id=audit_id,
        total_cases=len(request.cases),
        themes=[],
        uncategorized_case_ids=[c.id for c in request.cases],
    )


@v1.post("/emerging", response_model=EmergingResponse, tags=["emerging"])
async def detect_emerging(request: EmergingRequest) -> EmergingResponse:
    """Detect emerging or trending topics in recent cases."""
    audit_id = str(uuid.uuid4())
    # TODO: replace stub with real litellm call
    logger.info(
        "emerging_requested",
        audit_id=audit_id,
        total_recent=len(request.recent_cases),
    )
    return EmergingResponse(
        audit_id=audit_id,
        total_recent=len(request.recent_cases),
        total_baseline=len(request.baseline_cases) if request.baseline_cases else None,
        topics=[],
    )


@v1.post("/categories", response_model=CategoriesResponse, tags=["categories"])
async def suggest_categories(request: CategoriesRequest) -> CategoriesResponse:
    """Suggest a category taxonomy from support cases."""
    audit_id = str(uuid.uuid4())
    # TODO: replace stub with real litellm call
    logger.info(
        "categories_requested",
        audit_id=audit_id,
        total_cases=len(request.cases),
    )
    return CategoriesResponse(
        audit_id=audit_id,
        total_cases=len(request.cases),
        categories=[],
        unmapped_case_ids=[c.id for c in request.cases],
    )


@v1.post("/distribution", response_model=DistributionResponse, tags=["distribution"])
async def analyse_distribution(request: DistributionRequest) -> DistributionResponse:
    """Analyse distribution of cases across existing categories."""
    audit_id = str(uuid.uuid4())
    # TODO: replace stub with real litellm call
    logger.info(
        "distribution_requested",
        audit_id=audit_id,
        total_cases=len(request.cases),
    )
    return DistributionResponse(
        audit_id=audit_id,
        total_cases=len(request.cases),
        distribution=[],
        uncategorized_count=len(request.cases),
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


@app.post("/api/v1/ingest", response_model=IngestResult, tags=["ingest"])
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


@app.post("/api/v1/ingest/salesforce", response_model=IngestResult, tags=["ingest"])
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
        mapped = apply_mappings(records, custom_mappings)
    elif apply_defaults:
        mapped = apply_mappings(records, CASE_TO_TICKET)
    else:
        mapped = records

    errors: list[dict[str, Any]] = []
    cases: list[Case] = []

    for i, record in enumerate(mapped):
        try:
            cases.append(
                Case(
                    id=record.get("id", f"ingest-{i}"),
                    subject=record.get("subject", record.get("Subject", "Unknown")),
                    content=record.get(
                        "description", record.get("content", "No content")
                    ),
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
