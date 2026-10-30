"""ChatService end to end with a faked analytics connection.

Real planner, real SQL generation and validation; only database execution is faked. Proves the
``resultProfile`` the New Chat UI renders is derived from the executed rows, for many shapes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Industry, Settings
from app.semantic.service import SemanticService
from app.services.chat.query_cache import QUERY_CACHE
from app.services.chat.value_dictionary import ValueDictionarySnapshot
from tests.unit.test_chat_service_memory import _collect_stream, memory_chat  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "chat_routing_eval"))
from seed_values import seed_values_for_industry  # noqa: E402


class _Result:
    def __init__(self, rows: list[dict[str, Any]], columns: list[str]) -> None:
        self._rows, self._columns = rows, columns

    def mappings(self) -> _Result:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows

    def keys(self) -> list[str]:
        return self._columns

    def fetchall(self) -> list[tuple[str]]:
        return [("Seq Scan",)]

    def scalar_one_or_none(self) -> None:
        return None


def _months(n: int = 12) -> list[dict[str, Any]]:
    return [{"month": f"2024-{m:02d}-01", "revenue": 1_000_000 + m * 125_000} for m in range(1, n + 1)]


CASES: list[tuple[str, list[str], list[dict[str, Any]], str]] = [
    ("Total revenue", ["revenue"], [{"revenue": 987_654_321}], "single_value"),
    (
        "Top 3 models by units sold",
        ["model", "units_sold", "revenue"],
        [
            {"model": "Nexon", "units_sold": 9100, "revenue": 91_000_000},
            {"model": "Punch", "units_sold": 7400, "revenue": 52_000_000},
            {"model": "Harrier", "units_sold": 3300, "revenue": 70_000_000},
        ],
        "ranking",
    ),
    ("Revenue by month for 2024", ["month", "revenue"], _months(), "time_series"),
    (
        "Revenue by region",
        ["region_name", "revenue"],
        [{"region_name": "North", "revenue": 500}, {"region_name": "South", "revenue": 300}],
        "breakdown",
    ),
    (
        "Units sold by dealer",
        ["dealer_name", "units_sold"],
        [{"dealer_name": f"Dealer {i}", "units_sold": 5000 - i} for i in range(200)],
        "breakdown",
    ),
    ("Revenue by region", ["region_name", "revenue"], [], "empty"),
]


@pytest.fixture
def pack():
    return SemanticService(Settings())._load_pack(Industry.AUTOMOTIVE)


def _wire(service, pack, rows: list[dict[str, Any]], columns: list[str]) -> None:
    QUERY_CACHE.clear()
    service._semantic.get_pack = AsyncMock(return_value=pack)

    async def execute(statement, *args, **kwargs):  # noqa: ANN001
        return _Result(rows, columns)

    service._analytics.execute = AsyncMock(side_effect=execute)


def _event(events, name: str) -> dict[str, Any] | None:
    return next((data for ev, data in events if ev == name), None)


@pytest.mark.asyncio
@pytest.mark.parametrize(("question", "columns", "rows", "shape"), CASES)
async def test_result_profile_matches_executed_rows(
    memory_chat, pack, question, columns, rows, shape  # noqa: F811
) -> None:
    service, conv, _ = memory_chat
    _wire(service, pack, rows, columns)
    snapshot = ValueDictionarySnapshot(
        Industry.AUTOMOTIVE, seed_values_for_industry(Industry.AUTOMOTIVE)
    )
    with patch(
        "app.services.chat.service.get_value_dictionary", AsyncMock(return_value=snapshot)
    ):
        events = await _collect_stream(service, question, conv.id)

    meta = _event(events, "meta")
    assert meta is not None, [ev for ev, _ in events]
    assert _event(events, "sql") is not None, "data question must run governed SQL"
    profile = meta["resultProfile"]
    assert profile["shape"] == shape
    cap = min(service._settings.nlq_default_result_limit, service._settings.sql_max_result_rows)
    returned = rows[:cap]
    assert profile["rowCount"] == len(returned) == meta["rowCount"]
    assert profile["mayBeTruncated"] is (len(rows) > cap)

    sent_rows = _event(events, "rows")["rows"]
    assert sent_rows == returned

    # Every previewed label and figure is traceable to a returned row.
    labels = {
        " \u00b7 ".join(str(r[c])[:7] if c == "month" else str(r[c]) for c in profile["labelColumns"][:3])
        for r in returned
    }
    for shown in profile["preview"]:
        if shown["label"] is not None:
            assert shown["label"] in labels
        assert len(shown["values"]) <= 3
    if shape == "empty":
        assert profile["preview"] == []
        assert profile["chartSuitable"] is False
    if shape == "single_value":
        assert profile["chartSuitable"] is False
    if len(returned) > 5:
        assert len(profile["preview"]) == 5 and profile["previewTruncated"] is True


@pytest.mark.asyncio
async def test_follow_up_keeps_metric_and_profile(memory_chat, pack) -> None:
    service, conv, _ = memory_chat
    first_rows = [{"region_name": "North", "revenue": 500}, {"region_name": "South", "revenue": 300}]
    snapshot = ValueDictionarySnapshot(
        Industry.AUTOMOTIVE, seed_values_for_industry(Industry.AUTOMOTIVE)
    )
    with patch(
        "app.services.chat.service.get_value_dictionary", AsyncMock(return_value=snapshot)
    ):
        _wire(service, pack, first_rows, ["region_name", "revenue"])
        await _collect_stream(service, "Revenue by region", conv.id)
        _wire(service, pack, [{"region_name": "South", "revenue": 300}], ["region_name", "revenue"])
        events = await _collect_stream(service, "What about South?", conv.id)

    sql = _event(events, "sql")["sql"].lower()
    assert "south" in sql
    profile = _event(events, "meta")["resultProfile"]
    assert profile["rowCount"] == 1
    assert profile["preview"][0]["label"] == "South"
    assert profile["preview"][0]["values"][0]["text"].endswith("300")  # currency-formatted
