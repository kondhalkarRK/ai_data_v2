"""Response composition boundaries, independent of database and LLM providers."""

import pytest
from pydantic import ValidationError

from app.schemas.analytics_workspace import WorkspacePlan


def panel(kind="chart", dimension=True):
    return {
        "id": "sales",
        "title": "Sales",
        "kind": kind,
        "spec": {"metrics": ["revenue"], "dimensions": ["model"] if dimension else []},
    }


def test_single_value_has_no_forced_charts():
    plan = WorkspacePlan.model_validate(
        {"answerKind": "single_value", "title": "Sales", "panels": [panel("kpi", False)]}
    )
    assert len(plan.panels) == 1
    assert plan.panels[0].spec.dimensions == []


def test_clarification_has_no_execution_plan():
    plan = WorkspacePlan.model_validate(
        {
            "answerKind": "clarification",
            "title": "Clarify",
            "clarification": "Which metric and period?",
        }
    )
    assert plan.panels == []


@pytest.mark.parametrize(
    "patch",
    [
        {"answerKind": "single_value", "panels": [panel()]},
        {"answerKind": "analysis", "panels": []},
        {"answerKind": "analysis", "panels": [panel(), panel()]},
        {"answerKind": "clarification", "panels": [panel()], "clarification": "Which date?"},
        {"answerKind": "analysis", "panels": [panel("kpi")]},
        {"answerKind": "analysis", "panels": [panel("chart", False)]},
        {"answerKind": "analysis", "panels": [panel()], "sql": "SELECT 1"},
    ],
)
def test_invalid_composition_is_rejected(patch):
    with pytest.raises(ValidationError):
        WorkspacePlan.model_validate({"title": "Sales", **patch})
