"""Period label SQL for chat results."""

from app.services.chat.period_labels import period_label_sql
from app.services.chat.question_understanding import understand_question
from app.services.chat.templates import resolve_template
from app.core.config import Industry


def test_quarter_label_sql_uses_year_month_text() -> None:
    sql = period_label_sql("f.sales_date", "quarter")
    assert "to_char" in sql
    assert "YYYY-MM" in sql
    assert "date_trunc('quarter'" in sql


def test_half_label_sql() -> None:
    sql = period_label_sql("f.sales_date", "half")
    assert "INTERVAL '6 months'" in sql
    assert "YYYY-MM" in sql


def test_quarterly_maruti_plan_uses_label_in_template() -> None:
    plan = understand_question(
        Industry.AUTOMOTIVE,
        "Maruti quarterly sales by quarter",
    )
    assert "quarter" in plan.dimensions
    hit = resolve_template(Industry.AUTOMOTIVE, "Maruti quarterly sales", plan=plan)
    assert hit is not None
    assert "YYYY-MM" in hit.sql
    assert "date_trunc('quarter', f.sales_date)::date AS quarter" not in hit.sql
