"""describe_result: presentation hints derived only from the executed result."""

from __future__ import annotations

import re

import pytest

from app.services.chat.narration import describe_result


def _texts(profile: dict) -> list[list[str | None]]:
    return [[v["text"] for v in row["values"]] for row in profile["preview"]]


def test_empty_result() -> None:
    profile = describe_result(["region", "revenue"], [])
    assert profile["shape"] == "empty"
    assert profile["preview"] == []
    assert profile["chartSuitable"] is False


def test_single_value_has_no_chart() -> None:
    profile = describe_result(["total_revenue"], [{"total_revenue": 125_000_000}])
    assert profile["shape"] == "single_value"
    assert profile["chartSuitable"] is False
    assert _texts(profile) == [["\u20b912.50 Cr"]]
    assert profile["preview"][0]["label"] is None


def test_single_row_with_label_stays_single_value() -> None:
    profile = describe_result(
        ["make", "units_sold", "revenue"],
        [{"make": "Tata", "units_sold": 4321, "revenue": 51_000_000}],
    )
    assert profile["shape"] == "single_value"
    assert profile["preview"][0]["label"] == "Tata"
    assert _texts(profile) == [["4,321", "\u20b95.10 Cr"]]


def test_ranking_uses_plan_intent_and_keeps_result_order() -> None:
    rows = [
        {"model": "A", "units_sold": 900, "revenue": 9_000_000},
        {"model": "B", "units_sold": 700, "revenue": 8_000_000},
        {"model": "C", "units_sold": 500, "revenue": 4_000_000},
    ]
    profile = describe_result(["model", "units_sold", "revenue"], rows, intent="ranking")
    assert profile["shape"] == "ranking"
    assert [r["label"] for r in profile["preview"]] == ["A", "B", "C"]
    assert [m["column"] for m in profile["measures"]] == ["units_sold", "revenue"]
    assert [m["kind"] for m in profile["measures"]] == ["number", "currency"]
    assert profile["chartSuitable"] is True


def test_breakdown_when_no_ranking_hint() -> None:
    rows = [{"region": "North", "claims": 10}, {"region": "South", "claims": 20}]
    profile = describe_result(["region", "claims"], rows, intent="aggregation")
    assert profile["shape"] == "breakdown"


def test_comparison_from_plan_analysis() -> None:
    rows = [{"year": "2023", "revenue": 100}, {"year": "2024", "revenue": 150}]
    # "year" is a time label -> time series wins over the plan hint
    assert describe_result(["year", "revenue"], rows, analysis="year_window_compare")[
        "shape"
    ] == "time_series"
    rows = [{"make": "Tata", "revenue": 100}, {"make": "Kia", "revenue": 150}]
    profile = describe_result(["make", "revenue"], rows, analysis="brand_compare")
    assert profile["shape"] == "comparison"


def test_time_series_previews_latest_periods_in_order() -> None:
    rows = [{"month": f"2024-{m:02d}-01", "revenue": m * 1000} for m in range(1, 13)]
    profile = describe_result(["month", "revenue"], list(reversed(rows)), preview=4)
    assert profile["shape"] == "time_series"
    assert [r["label"] for r in profile["preview"]] == [
        "2024-09",
        "2024-10",
        "2024-11",
        "2024-12",
    ]
    assert profile["previewTruncated"] is True
    assert _texts(profile)[-1] == ["\u20b912,000"]


def test_percent_measure_scaling() -> None:
    rows = [{"region": "N", "loss_ratio": 0.42}, {"region": "S", "loss_ratio": 0.61}]
    profile = describe_result(["region", "loss_ratio"], rows)
    assert profile["measures"][0]["kind"] == "percent"
    assert _texts(profile) == [["42.0%"], ["61.0%"]]


def test_text_only_result_is_table_without_chart() -> None:
    rows = [{"dealer": "D1", "city": "Pune"}, {"dealer": "D2", "city": "Delhi"}]
    profile = describe_result(["dealer", "city"], rows)
    assert profile["shape"] == "table"
    assert profile["chartSuitable"] is False
    assert profile["measures"] == []


def test_large_result_flags_truncation_and_limits_preview() -> None:
    rows = [{"dealer": f"D{i}", "units_sold": 1000 - i} for i in range(200)]
    profile = describe_result(["dealer", "units_sold"], rows, row_limit=200, preview=5)
    assert profile["rowCount"] == 200
    assert len(profile["preview"]) == 5
    assert profile["previewTruncated"] is True
    assert profile["mayBeTruncated"] is True


@pytest.mark.parametrize(
    ("columns", "rows", "intent"),
    [
        (["region", "revenue"], [{"region": "N", "revenue": 1234567}, {"region": "S", "revenue": 87}], None),
        (["model", "units_sold"], [{"model": "X", "units_sold": 12}, {"model": "Y", "units_sold": 7}], "ranking"),
        (["month", "claims"], [{"month": "2024-01-01", "claims": 3}, {"month": "2024-02-01", "claims": 9}], None),
        (["segment", "premium", "claims"], [{"segment": "A", "premium": 5.5, "claims": 2}, {"segment": "B", "premium": 9.25, "claims": 4}], None),
    ],
)
def test_every_displayed_number_comes_from_a_result_row(columns, rows, intent) -> None:
    """No invented numbers: each preview figure formats a value present in the rows."""
    profile = describe_result(columns, rows, intent=intent)
    allowed = {float(v) for row in rows for v in row.values() if isinstance(v, (int, float))}
    for row, shown in zip(rows, profile["preview"], strict=True):
        for value in shown["values"]:
            digits = re.sub(r"[^\d.]", "", value["text"] or "")
            assert digits
            raw = float(row[value["column"]])
            assert raw in allowed
            # compact units (L / Cr) are scaled; plain values must match exactly
            if "Cr" not in value["text"] and "L" not in value["text"] and "%" not in value["text"]:
                assert float(digits.replace(",", "")) == pytest.approx(raw, abs=0.01)
