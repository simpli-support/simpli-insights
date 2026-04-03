"""FastAPI application."""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

from simpli_insights import __version__
from simpli_core import CostTracker, create_app
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
