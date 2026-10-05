from __future__ import annotations

from app.db.schema_repair import plan_auth_user_industry_repair, plan_llm_usage_repair

CURRENT_COLUMNS = {
    "usage_id",
    "user_id",
    "question",
    "model_name",
    "execution_mode",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "response_time_ms",
    "industry",
    "query_history_id",
    "estimated_cost_usd",
    "purpose",
    "created_at",
}
CURRENT_CONSTRAINTS = {
    "pk_llm_usage",
    "fk_llm_usage_user_id_auth_users",
    "ck_llm_usage_execution_mode",
}


def test_current_table_needs_nothing() -> None:
    assert plan_llm_usage_repair(CURRENT_COLUMNS, CURRENT_CONSTRAINTS) == []


def test_legacy_table_is_upgraded() -> None:
    legacy = {
        "id",
        "user_id",
        "industry",
        "model",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "estimated_cost_usd",
        "purpose",
        "created_at",
    }
    steps = plan_llm_usage_repair(legacy, {"pk_llm_usage", "fk_llm_usage_user"})
    joined = "\n".join(steps)
    assert "RENAME COLUMN id TO usage_id" in joined
    assert "RENAME COLUMN model TO model_name" in joined
    for column in ("question", "execution_mode", "response_time_ms", "query_history_id"):
        assert f"ADD COLUMN {column}" in joined
    assert "DROP CONSTRAINT fk_llm_usage_user" in joined
    assert "fk_llm_usage_user_id_auth_users" in joined
    assert "ck_llm_usage_execution_mode" in joined


def test_partially_upgraded_table_only_adds_missing_parts() -> None:
    columns = CURRENT_COLUMNS - {"execution_mode", "query_history_id"}
    steps = plan_llm_usage_repair(columns, CURRENT_CONSTRAINTS - {"ck_llm_usage_execution_mode"})
    joined = "\n".join(steps)
    assert "RENAME" not in joined
    assert "ADD COLUMN execution_mode" in joined
    assert "ADD COLUMN query_history_id" in joined
    assert "ADD COLUMN question" not in joined


def test_uppercase_industry_values_are_normalized() -> None:
    steps = plan_auth_user_industry_repair()
    joined = "\n".join(steps)
    assert "UPDATE auth_users" in joined
    assert "LOWER(default_industry)" in joined
    assert "default_industry <> LOWER(default_industry)" in joined
