"""Unit tests for trust score, templates and knowledge chunking."""

from __future__ import annotations

from app.core.config import Industry
from app.services.chat.templates import resolve_template
from app.services.chat.trust import compute_trust_score
from app.services.knowledge import chunk_text


def test_trust_score_four_components_and_empty_cap() -> None:
    score, breakdown = compute_trust_score(
        glossary_matches=2,
        glossary_hints_are_sql=True,
        resolution_path="template",
        row_count=10,
    )
    assert score == 100
    assert breakdown["semantic"] == 25
    empty_score, empty_breakdown = compute_trust_score(
        glossary_matches=2,
        glossary_hints_are_sql=True,
        resolution_path="template",
        row_count=0,
    )
    assert empty_score == 45
    assert empty_breakdown["empty_cap"] is True


def test_templates_resolve_for_both_industries() -> None:
    ins = resolve_template(Industry.INSURANCE, "What is the loss ratio?")
    assert ins is not None
    assert "fact_claims" in ins.sql
    auto = resolve_template(Industry.AUTOMOTIVE, "Show revenue by month")
    assert auto is not None
    assert "fact_sales" in auto.sql


def test_chunk_text_respects_max_and_overlap() -> None:
    text = "word " * 500
    chunks = chunk_text(text, max_chars=200, min_chars=40, overlap=40)
    assert len(chunks) > 1
    assert all(len(chunk) <= 200 for chunk in chunks)
