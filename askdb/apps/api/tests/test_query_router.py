from app.core.config import Industry
from app.services.chat.query_router import plan_entities, route_question
from app.services.chat.question_understanding import ExtractedFilter, QuestionPlan


def _plan(**kwargs: object) -> QuestionPlan:
    defaults: dict[str, object] = {
        "industry": Industry.AUTOMOTIVE,
        "intent": "ranking",
        "entity": "vehicle",
        "metric": "sales",
    }
    defaults.update(kwargs)
    return QuestionPlan(**defaults)  # type: ignore[arg-type]


def test_metric_question_routes_sql() -> None:
    decision = route_question(
        "top selling SUV in Mumbai",
        _plan(
            intent="ranking",
            filters=[
                ExtractedFilter(
                    column="region", operator="=", value="Mumbai", label="Mumbai"
                )
            ],
        ),
    )
    assert decision.route == "sql"


def test_document_cues_route_knowledge() -> None:
    decision = route_question(
        "What are the key findings in the dealer report?",
        _plan(intent="lookup", metric="unknown", entity="unknown"),
    )
    assert decision.route == "knowledge"


def test_why_question_routes_hybrid() -> None:
    decision = route_question(
        "Why did SUV sales drop in Mumbai?",
        _plan(
            intent="aggregation",
            filters=[
                ExtractedFilter(
                    column="region", operator="=", value="Mumbai", label="Mumbai"
                )
            ],
        ),
    )
    assert decision.route == "hybrid"


def test_insights_cue_routes_hybrid() -> None:
    decision = route_question("What insights explain the increase in bookings?", _plan())
    assert decision.route == "hybrid"


def test_unknown_defaults_to_sql_not_rag() -> None:
    decision = route_question(
        "hello there",
        _plan(intent="lookup", metric="unknown", entity="unknown", filters=[]),
        has_documents=True,
    )
    assert decision.route == "sql"


def test_document_like_without_metric_is_knowledge() -> None:
    decision = route_question(
        "summarize the uploaded policy memo",
        _plan(intent="lookup", metric="unknown", entity="unknown"),
    )
    assert decision.route == "knowledge"


def test_plan_entities_from_filters() -> None:
    plan = _plan(
        filters=[
            ExtractedFilter(column="region", operator="=", value="Mumbai", label="Mumbai")
        ]
    )
    assert "Mumbai" in plan_entities(plan)
