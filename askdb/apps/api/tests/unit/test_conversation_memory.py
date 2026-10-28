"""Compact session memory: isolation, expiry, pending clarification, RBAC revalidation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import Industry, Settings
from app.services.chat.conversation_context import plan_state, state_to_plan
from app.services.chat.conversation_memory import (
    analytical_expired,
    append_recent_turn,
    assert_memory_scope,
    build_analytical_context,
    empty_memory,
    follow_up_context_status,
    is_refresh_request,
    revalidate_plan_for_scope,
    revalidate_prior_state_for_scope,
    revalidate_stored_plan_for_scope,
    resolve_incoming_message,
    ResultMeta,
    set_pending_clarification,
    validated_plan_is_structured,
)
from app.services.chat.question_understanding import ExtractedFilter, QuestionPlan
from app.services.security.region_scope import RegionScope


def _settings(**overrides: int) -> Settings:
    base = Settings()
    return base.model_copy(
        update={
            "chat_analytical_context_max_turns": overrides.get("max_turns", 8),
            "chat_analytical_context_ttl_seconds": overrides.get("ttl", 1800),
            "chat_recent_turns_window": overrides.get("window", 6),
        }
    )


def _sample_plan(*, filters: tuple[ExtractedFilter, ...] = ()) -> QuestionPlan:
    return QuestionPlan(
        industry=Industry.AUTOMOTIVE,
        metric="revenue",
        entity="metric_only",
        intent="aggregation",
        dimensions=("region",),
        time_grain=None,
        filters=filters,
    )


def test_memory_scope_isolated_per_user_and_conversation() -> None:
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    conv_a = uuid.uuid4()
    conv_b = uuid.uuid4()
    conv_a2 = uuid.uuid4()
    mem_a = empty_memory(user_id=user_a, conversation_id=conv_a)
    mem_b = empty_memory(user_id=user_b, conversation_id=conv_b)
    mem_a2 = empty_memory(user_id=user_a, conversation_id=conv_a2)
    assert_memory_scope(mem_a, user_id=user_a, conversation_id=conv_a)
    assert_memory_scope(mem_b, user_id=user_b, conversation_id=conv_b)
    assert_memory_scope(mem_a2, user_id=user_a, conversation_id=conv_a2)
    with pytest.raises(PermissionError):
        assert_memory_scope(mem_a, user_id=user_b, conversation_id=conv_a)
    with pytest.raises(PermissionError):
        assert_memory_scope(mem_a, user_id=user_a, conversation_id=conv_b)
    with pytest.raises(PermissionError):
        assert_memory_scope(mem_a, user_id=user_a, conversation_id=conv_a2)


def test_analytical_context_expires_by_turn_count() -> None:
    settings = _settings(max_turns=3)
    mem = empty_memory(user_id=uuid.uuid4(), conversation_id=uuid.uuid4())
    plan = _sample_plan()
    mem.analytical = build_analytical_context(
        plan=plan,
        question="Revenue by region",
        result_meta=ResultMeta(row_count=4, column_names=("region", "revenue")),
        prior=None,
    )
    mem.analytical.turn_counter = 3
    assert analytical_expired(mem, settings) is True
    assert follow_up_context_status(mem, "What about South?", settings) == "expired"


def test_analytical_context_expires_by_ttl() -> None:
    settings = _settings(ttl=60)
    mem = empty_memory(user_id=uuid.uuid4(), conversation_id=uuid.uuid4())
    plan = _sample_plan()
    ctx = build_analytical_context(
        plan=plan,
        question="Revenue by region",
        result_meta=ResultMeta(),
        prior=None,
    )
    ctx.updated_at = datetime.now(UTC) - timedelta(seconds=120)
    mem.analytical = ctx
    assert analytical_expired(mem, settings, now=datetime.now(UTC)) is True


def test_pending_clarification_completes_on_short_answer() -> None:
    mem = empty_memory(user_id=uuid.uuid4(), conversation_id=uuid.uuid4())
    set_pending_clarification(
        mem,
        original_question="Show sales",
        clarifies="Which metric?",
        options=["Revenue", "Units"],
    )
    effective, completed = resolve_incoming_message(mem, "Revenue")
    assert completed is True
    assert effective == "Show sales Revenue"
    assert mem.pending is None


def test_pending_clarification_abandoned_on_clearly_non_data() -> None:
    mem = empty_memory(user_id=uuid.uuid4(), conversation_id=uuid.uuid4())
    set_pending_clarification(
        mem,
        original_question="Show sales",
        clarifies="Which metric?",
        options=["Revenue", "Units"],
    )
    effective, completed = resolve_incoming_message(
        mem, "What is the weather in Mumbai today?"
    )
    assert completed is False
    assert effective.startswith("What is the weather")
    assert mem.pending is None


def test_pending_not_abandoned_on_ambiguous_long_data_question() -> None:
    mem = empty_memory(user_id=uuid.uuid4(), conversation_id=uuid.uuid4())
    set_pending_clarification(
        mem,
        original_question="Show sales",
        clarifies="Which metric?",
        options=["Revenue", "Units"],
    )
    effective, completed = resolve_incoming_message(mem, "Revenue by region last quarter")
    assert completed is True
    assert "Show sales" in effective
    assert mem.pending is None


def test_refresh_explicit_cues_only() -> None:
    assert is_refresh_request("refresh that")
    assert is_refresh_request("Please reload the data")
    assert is_refresh_request("update the numbers")
    assert is_refresh_request("re-run that query")
    assert not is_refresh_request("revenue for the latest quarter")
    assert not is_refresh_request("Give me the latest revenue")
    assert not is_refresh_request("latest")


def test_latest_quarter_follow_up_keeps_context() -> None:
    settings = _settings()
    mem = empty_memory(user_id=uuid.uuid4(), conversation_id=uuid.uuid4())
    mem.analytical = build_analytical_context(
        plan=_sample_plan(),
        question="revenue for the latest quarter",
        result_meta=ResultMeta(),
        prior=None,
    )
    assert not is_refresh_request("revenue for the latest quarter")
    assert follow_up_context_status(mem, "What about South?", settings) == "active"


def test_recent_turns_window_truncates() -> None:
    settings = _settings(window=3)
    mem = empty_memory(user_id=uuid.uuid4(), conversation_id=uuid.uuid4())
    for i in range(5):
        append_recent_turn(mem, role="user", text=f"turn {i}", settings=settings)
    assert len(mem.recent_turns) == 3
    assert mem.recent_turns[0]["text"] == "turn 2"


def test_validated_plan_structured_no_free_text_blob() -> None:
    mem = empty_memory(user_id=uuid.uuid4(), conversation_id=uuid.uuid4())
    mem.analytical = build_analytical_context(
        plan=_sample_plan(
            filters=(
                ExtractedFilter(
                    column="region_name",
                    operator="=",
                    value="South",
                    values=("South",),
                    label="South",
                ),
            )
        ),
        question="Revenue in South",
        result_meta=ResultMeta(row_count=1, column_names=("revenue",)),
        prior=None,
    )
    blob = mem.to_dict()
    plan_dict = blob["analytical"]["validatedPlan"]
    assert validated_plan_is_structured(plan_dict)
    assert "sql" not in str(plan_dict).lower()
    assert "previousQuestion" not in plan_dict
    assert blob["analytical"]["previousQuestion"] == "Revenue in South"


def test_rbac_revalidation_blocks_forbidden_region_on_follow_up() -> None:
    scope = RegionScope(unrestricted=False, zones=("North",))
    mem = empty_memory(user_id=uuid.uuid4(), conversation_id=uuid.uuid4())
    plan = _sample_plan(
        filters=(
            ExtractedFilter(
                column="region_name",
                operator="=",
                value="North",
                values=("North",),
                label="North",
            ),
        )
    )
    mem.analytical = build_analytical_context(
        plan=plan,
        question="Revenue in North",
        result_meta=ResultMeta(),
        prior=None,
    )
    ok, reason = revalidate_stored_plan_for_scope(
        mem, Industry.AUTOMOTIVE, "What about South?", scope
    )
    assert ok is False
    assert reason is not None
    assert "South" in reason


def test_history_fallback_state_uses_same_rbac_helper() -> None:
    scope = RegionScope(unrestricted=False, zones=("North",))
    state = plan_state(_sample_plan())
    ok, reason = revalidate_prior_state_for_scope(
        Industry.AUTOMOTIVE, state, "What about South?", scope
    )
    assert ok is False
    assert reason is not None


def test_rbac_revalidation_on_resolved_plan() -> None:
    scope = RegionScope(unrestricted=False, zones=("North",))
    state = plan_state(_sample_plan())
    plan = state_to_plan(Industry.AUTOMOTIVE, state)
    ok, _ = revalidate_plan_for_scope(plan, "Compare North and South", scope)
    assert ok is False
