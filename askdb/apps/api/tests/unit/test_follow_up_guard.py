"""Stage C: short follow-ups only reuse the prior plan when they name something governed."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

from app.core.config import Industry, Settings
from app.semantic.service import SemanticService
from app.services.chat.conversation_memory import (
    ResultMeta,
    build_analytical_context,
    empty_memory,
)
from app.services.chat.follow_up_guard import follow_up_guard_allows_sql
from app.services.chat.question_understanding import QuestionPlan
from app.services.chat.value_dictionary import ValueDictionarySnapshot

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "chat_routing_eval"))
from seed_values import seed_values_for_industry  # noqa: E402

_PRIOR = {"metric": "revenue", "entity": "metric_only", "intent": "aggregation",
          "dimensions": ["region"]}


@pytest.fixture(scope="module")
def automotive() -> tuple[ValueDictionarySnapshot, object]:
    pack = SemanticService(Settings())._load_pack(Industry.AUTOMOTIVE)
    snapshot = ValueDictionarySnapshot(
        Industry.AUTOMOTIVE, seed_values_for_industry(Industry.AUTOMOTIVE)
    )
    return snapshot, pack


def _active_memory():
    mem = empty_memory(user_id=uuid.uuid4(), conversation_id=uuid.uuid4())
    mem.analytical = build_analytical_context(
        plan=QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            metric="revenue",
            entity="metric_only",
            intent="aggregation",
            dimensions=("region",),
        ),
        question="Revenue by region",
        result_meta=ResultMeta(row_count=4),
        prior=None,
    )
    return mem


def _check(question: str, automotive) -> tuple[bool, str | None]:
    snapshot, pack = automotive
    return follow_up_guard_allows_sql(
        question=question,
        session_memory=_active_memory(),
        settings=Settings(),
        prior_state=_PRIOR,
        snapshot=snapshot,
        pack=pack,
        industry=Industry.AUTOMOTIVE,
    )


def test_known_value_allowed_with_interpretation(automotive) -> None:
    allowed, interp = _check("What about South?", automotive)
    assert allowed
    assert interp == "Showing revenue for South"


@pytest.mark.parametrize(
    "question",
    ["Break it down by month", "Bottom 5 instead", "By quarter", "Last year?", "Add Delhi",
     "Same for units"],
)
def test_operations_dates_and_metrics_allowed(question: str, automotive) -> None:
    assert _check(question, automotive)[0]


@pytest.mark.parametrize("question", ["What about dinner?", "And the cat?", "What about it?"])
def test_unanchored_follow_up_blocked(question: str, automotive) -> None:
    assert _check(question, automotive) == (False, None)


def test_value_from_other_industry_is_not_an_anchor(automotive) -> None:
    # "Repudiated" is an insurance claim status; it must not anchor an automotive follow-up.
    assert _check("What about Repudiated?", automotive) == (False, None)


def test_no_prior_context_is_not_guarded(automotive) -> None:
    snapshot, pack = automotive
    allowed, _ = follow_up_guard_allows_sql(
        question="What about dinner?",
        session_memory=empty_memory(user_id=uuid.uuid4(), conversation_id=uuid.uuid4()),
        settings=Settings(),
        prior_state=None,
        snapshot=snapshot,
        pack=pack,
        industry=Industry.AUTOMOTIVE,
    )
    assert allowed
