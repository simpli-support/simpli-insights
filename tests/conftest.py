"""Shared test fixtures for simpli-insights."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_llm_response(content: str) -> MagicMock:
    resp = MagicMock()
    choice = MagicMock()
    choice.message.content = content
    resp.choices = [choice]
    resp.usage.prompt_tokens = 10
    resp.usage.completion_tokens = 20
    resp.usage.total_tokens = 30
    resp.model = "mock-model"
    return resp


_MOCK_RESPONSES: dict[str, dict[str, Any]] = {
    "theme analyst": {
        "themes": [
            {
                "name": "Password Issues",
                "description": "Login problems",
                "frequency": 10,
                "representative_cases": ["c-1"],
                "severity": "medium",
            }
        ]
    },
    "trend detector": {
        "topics": [
            {
                "name": "New Feature",
                "case_count": 5,
                "growth_rate": 1.5,
                "first_seen": "2026-01-01",
                "risk_level": "low",
            }
        ]
    },
    "taxonomy designer": {
        "categories": [
            {
                "name": "Technical",
                "description": "Tech issues",
                "parent": None,
                "estimated_percentage": 0.4,
            }
        ]
    },
    "distribution analyst": {
        "distribution": [{"category": "Technical", "count": 10, "percentage": 0.5}],
        "uncategorized_count": 2,
    },
}

_DEFAULT_RESPONSE: dict[str, Any] = {"status": "ok"}


async def _fake_acompletion(**kwargs: Any) -> MagicMock:
    messages = kwargs.get("messages", [])
    system_text = ""
    for msg in messages:
        if msg.get("role") == "system":
            system_text = msg.get("content", "").lower()
            break
    for keyword, response in _MOCK_RESPONSES.items():
        if keyword in system_text:
            return _mock_llm_response(json.dumps(response))
    return _mock_llm_response(json.dumps(_DEFAULT_RESPONSE))


@pytest.fixture(autouse=True)
def _mock_litellm() -> Any:
    with patch(
        "litellm.acompletion", new_callable=AsyncMock, side_effect=_fake_acompletion
    ):
        yield
