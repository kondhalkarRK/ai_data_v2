"""Executive narration built from result rows."""

from app.services.chat.narration import narrate


def test_two_period_comparison_reads_like_an_executive_summary() -> None:
    story = narrate(
        ["year", "revenue"],
        [{"year": 2024, "revenue": 106_000_000}, {"year": 2025, "revenue": 125_000_000}],
    )
    assert story is not None
    assert story.summary == (
        "Revenue reached \u20b912.50 Cr in 2025, up 18% on 2024, "
        "making 2025 the stronger of the two periods."
    )


def test_growing_trend_has_momentum_insight_and_focus() -> None:
    rows = [{"month": f"2025-{m:02d}-01", "units_sold": 100 + m * 12} for m in range(1, 9)]
    story = narrate(["month", "units_sold"], rows)
    assert story is not None
    assert "across the period" in story.summary
    assert "2025-08 was the strongest period" in story.summary
    assert story.insight and "Momentum is building" in story.insight
    assert story.focus
    assert any(item.startswith("Total across 8 periods") for item in story.highlights)


def test_sharp_last_period_drop_is_flagged_as_possibly_partial() -> None:
    rows = [{"month": f"2025-{m:02d}", "revenue": 1_000_000} for m in range(1, 6)]
    rows.append({"month": "2025-06", "revenue": 200_000})
    story = narrate(["month", "revenue"], rows)
    assert story is not None and story.insight
    assert "partial" in story.insight


def test_ranking_reports_leader_share_concentration_and_laggard() -> None:
    rows = [
        {"region": "West", "revenue": 400},
        {"region": "North", "revenue": 300},
        {"region": "South", "revenue": 150},
        {"region": "East", "revenue": 100},
        {"region": "Central", "revenue": 50},
    ]
    story = narrate(["region", "revenue"], rows)
    assert story is not None
    assert story.summary.startswith("West")
    assert "40% of the total" in story.summary
    assert any("Top 3" in item for item in story.highlights)
    assert story.insight and "concentrated" in story.insight
    assert story.focus and "Central" in story.focus


def test_ratio_metrics_are_shown_as_percentages_without_shares() -> None:
    rows = [
        {"region_name": "North", "loss_ratio": 0.72},
        {"region_name": "South", "loss_ratio": 0.55},
        {"region_name": "West", "loss_ratio": 0.48},
    ]
    story = narrate(["region_name", "loss_ratio"], rows)
    assert story is not None
    assert story.summary == "North has the highest loss ratio at 72.0%, 17.0 pts above South."
    assert story.focus and story.focus.startswith("Prioritise North")
    assert any("West is the best" in item for item in story.highlights)


def test_single_value_and_non_numeric_results() -> None:
    single = narrate(["total_revenue"], [{"total_revenue": 45_000_000}])
    assert single is not None
    assert single.summary == "Total revenue stands at \u20b94.50 Cr for the selection."
    assert narrate(["dealer_name"], [{"dealer_name": "Alpha"}]) is None


def test_phrasing_varies_between_results() -> None:
    summaries = set()
    for brand in ("Tata", "Mahindra", "Hyundai", "Kia", "Maruti", "Honda"):
        story = narrate(
            ["make", "units_sold"],
            [{"make": brand, "units_sold": 900}, {"make": "Other", "units_sold": 400}],
        )
        assert story is not None
        summaries.add(story.summary.split(brand, 1)[1].split(" units")[0])
    assert len(summaries) > 1
