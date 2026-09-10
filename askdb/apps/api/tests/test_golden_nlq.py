"""Golden routing coverage for deterministic NLQ parity."""

import pytest

from app.core.config import Industry
from app.services.chat.intents import is_out_of_bounds, needs_clarification
from app.services.chat.templates import resolve_template


@pytest.mark.parametrize(
    ("industry", "question"),
    [
        (Industry.INSURANCE, "Show loss ratio"),
        (Industry.INSURANCE, "Loss ratio by month"),
        (Industry.INSURANCE, "How many claims are there?"),
        (Industry.INSURANCE, "Claim volume by status"),
        (Industry.INSURANCE, "Show written premium"),
        (Industry.INSURANCE, "Earned premium by month"),
        (Industry.INSURANCE, "Show GWP"),
        (Industry.INSURANCE, "Claims by region"),
        (Industry.INSURANCE, "Top region by incurred claims"),
        (Industry.INSURANCE, "Show me"),
        (Industry.INSURANCE, "Dashboard"),
        (Industry.INSURANCE, "What is the weather tomorrow?"),
        (Industry.AUTOMOTIVE, "Revenue by month"),
        (Industry.AUTOMOTIVE, "Show total sales"),
        (Industry.AUTOMOTIVE, "Top models"),
        (Industry.AUTOMOTIVE, "Best selling cars"),
        (Industry.AUTOMOTIVE, "Show electric vehicle share"),
        (Industry.AUTOMOTIVE, "Dealer performance"),
        (Industry.AUTOMOTIVE, "Who won the football match?"),
        (Industry.AUTOMOTIVE, "Give me a recipe"),
    ],
)
def test_golden_question_has_known_path(industry: Industry, question: str) -> None:
    assert (
        resolve_template(industry, question) is not None
        or is_out_of_bounds(question, industry)
        or needs_clarification(question) is not None
    )
