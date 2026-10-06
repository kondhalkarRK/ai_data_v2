"""Region row-level security for every warehouse query.

Access is granted as North / South / East / West *zones*. The automotive and
insurance warehouses store city-level ``dim_region`` rows, so a zone is the set of
those rows whose state maps into it. Enforcement happens by rewriting SQL that
touches region-bearing tables — UI hiding is only a convenience.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession
from sqlalchemy.sql.elements import TextClause

from app.core.config import Industry
from app.core.exceptions import AuthorizationError
from app.models.enums import Role
from app.models.region_access import UserRegionAccess
from app.models.user import User
from app.services.governance.audit import AdminAction, record_admin_action

logger = logging.getLogger(__name__)

ZONES: tuple[str, ...] = ("North", "South", "East", "West")
_ZONE_SET = frozenset(ZONES)

NORTH_STATES = frozenset({"DL", "HR", "UP", "PB", "CH", "UK", "HP", "RJ", "JK", "LA", "UT"})
SOUTH_STATES = frozenset({"KA", "TN", "KL", "TS", "TG", "AP", "PY"})
EAST_STATES = frozenset({"WB", "BR", "JH", "OD", "AS", "NL", "MN", "MZ", "TR", "ML", "SK", "AR"})
WEST_STATES = frozenset({"MH", "GJ", "GA", "MP", "CG", "DD", "DN", "LD"})

NORTH_STATE_NAMES = frozenset(
    {
        "delhi",
        "haryana",
        "uttar pradesh",
        "punjab",
        "chandigarh",
        "uttarakhand",
        "himachal pradesh",
        "rajasthan",
        "jammu and kashmir",
        "ladakh",
    }
)
SOUTH_STATE_NAMES = frozenset(
    {"karnataka", "tamil nadu", "kerala", "telangana", "andhra pradesh", "puducherry"}
)
EAST_STATE_NAMES = frozenset(
    {
        "west bengal",
        "bihar",
        "jharkhand",
        "odisha",
        "assam",
        "nagaland",
        "manipur",
        "mizoram",
        "tripura",
        "meghalaya",
        "sikkim",
        "arunachal pradesh",
    }
)

CITY_ZONE: dict[str, str] = {
    "new delhi": "North",
    "delhi": "North",
    "noida": "North",
    "gurugram": "North",
    "gurgaon": "North",
    "jaipur": "North",
    "lucknow": "North",
    "chandigarh": "North",
    "kanpur": "North",
    "varanasi": "North",
    "dehradun": "North",
    "shimla": "North",
    "ludhiana": "North",
    "jodhpur": "North",
    "mumbai": "West",
    "pune": "West",
    "ahmedabad": "West",
    "surat": "West",
    "indore": "West",
    "bhopal": "West",
    "nagpur": "West",
    "nashik": "West",
    "vadodara": "West",
    "rajkot": "West",
    "goa": "West",
    "raipur": "West",
    "bengaluru": "South",
    "bangalore": "South",
    "hyderabad": "South",
    "chennai": "South",
    "kochi": "South",
    "coimbatore": "South",
    "madurai": "South",
    "visakhapatnam": "South",
    "vijayawada": "South",
    "thiruvananthapuram": "South",
    "trivandrum": "South",
    "mangaluru": "South",
    "mysuru": "South",
    "kolkata": "East",
    "patna": "East",
    "ranchi": "East",
    "bhubaneswar": "East",
    "guwahati": "East",
}

_ZONE_WORD = re.compile(r"\b(north|south|east|west)\b", re.I)
_SQL_KEYWORDS = frozenset(
    {
        "ON",
        "WHERE",
        "JOIN",
        "LEFT",
        "RIGHT",
        "INNER",
        "FULL",
        "CROSS",
        "GROUP",
        "ORDER",
        "LIMIT",
        "HAVING",
        "UNION",
        "EXCEPT",
        "INTERSECT",
        "SET",
        "AS",
        "AND",
        "OR",
        "USING",
        "NATURAL",
        "OUTER",
        "SELECT",
        "WITH",
        "RETURNING",
        "WINDOW",
        "FETCH",
        "OFFSET",
        "FOR",
    }
)

_SCOPED_TABLES = (
    "automotive.dim_region",
    "automotive.dim_dealer",
    "automotive.fact_sales",
    "automotive.fact_forecast_monthly",
    "insurance.dim_region",
    "insurance.dim_policy",
    "insurance.fact_claims",
    "insurance.fact_policy_monthly",
    "insurance.fact_operating_expense_monthly",
    "insurance.fact_forecast_monthly",
)
_DIM_REGION = frozenset({"automotive.dim_region", "insurance.dim_region"})
_TABLE_RE = re.compile(
    r"\b(FROM|JOIN)\s+(" + "|".join(re.escape(t) for t in _SCOPED_TABLES) + r")"
    r"(?:\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*))?",
    re.IGNORECASE,
)

_GEO_COLUMNS = (
    "region_name",
    "dim_region",
    "state_code",
    "state_name",
    "city",
)


class RegionAccessDeniedError(AuthorizationError):
    code = "region_forbidden"
    message = "You do not have access to that region."


@dataclass(frozen=True, slots=True)
class RegionScope:
    unrestricted: bool
    zones: tuple[str, ...]
    user_id: UUID | None = None
    username: str | None = None

    @classmethod
    def all_regions(cls, user: User | None = None) -> RegionScope:
        return cls(
            unrestricted=True,
            zones=ZONES,
            user_id=getattr(user, "id", None),
            username=getattr(user, "username", None),
        )

    @property
    def restricted(self) -> bool:
        return not self.unrestricted

    @property
    def hide_region_filter(self) -> bool:
        return self.restricted

    def cache_key(self) -> str:
        if self.unrestricted:
            return "all"
        return ",".join(self.zones) or "none"

    def allows_zone(self, zone: str | None) -> bool:
        if self.unrestricted or not zone:
            return True
        return _canonical_zone(zone) in self.zones

    def allows_label(self, label: str | None) -> bool:
        if self.unrestricted or not label:
            return True
        zone = zone_for_label(label)
        if zone is None:
            return True
        return zone in self.zones

    def dim_predicate(self, industry: Industry) -> str:
        expr = zone_sql_expression(industry)
        allowed = ", ".join(f"'{z}'" for z in self.zones)
        return f"({expr}) IN ({allowed})"

    def apply_sql(self, sql: str, industry: Industry) -> str:
        return apply_region_sql(sql, industry, self)

    def filter_labels(self, labels: list[str]) -> list[str]:
        if self.unrestricted:
            return labels
        return [item for item in labels if self.allows_label(item)]

    def to_api(self) -> dict[str, Any]:
        return {
            "unrestricted": self.unrestricted,
            "zones": list(self.zones if not self.unrestricted else ZONES),
            "hide_region_filter": self.hide_region_filter,
        }

    def deny_message(self, attempted: str | None = None) -> str:
        allowed = " and ".join(self.zones) if self.zones else "no"
        if attempted:
            return f"Access denied. You only have access to {allowed} region data."
        return f"You only have access to {allowed} region data."


def _canonical_zone(raw: str) -> str | None:
    token = (raw or "").strip().title()
    return token if token in _ZONE_SET else None


def zone_for_state_code(code: str | None) -> str | None:
    if not code:
        return None
    token = code.strip().upper()
    if token in NORTH_STATES:
        return "North"
    if token in SOUTH_STATES:
        return "South"
    if token in EAST_STATES:
        return "East"
    if token in WEST_STATES:
        return "West"
    return None


def zone_for_state_name(name: str | None) -> str | None:
    if not name:
        return None
    token = name.strip().casefold()
    if token in NORTH_STATE_NAMES:
        return "North"
    if token in SOUTH_STATE_NAMES:
        return "South"
    if token in EAST_STATE_NAMES:
        return "East"
    return "West"


def zone_for_place(text: str | None) -> str | None:
    if not text:
        return None
    key = text.strip().casefold()
    if key in CITY_ZONE:
        return CITY_ZONE[key]
    for token, zone in CITY_ZONE.items():
        if token in key:
            return zone
    return zone_for_state_code(text) or zone_for_state_name(text)


def zone_for_label(label: str | None) -> str | None:
    """Map a UI / NL value (zone, city, region_name, state) to a security zone."""
    if not label:
        return None
    direct = _canonical_zone(label)
    if direct:
        return direct
    return zone_for_place(label)


def zone_sql_expression(industry: Industry, alias: str | None = None) -> str:
    prefix = f"{alias}." if alias else ""
    if industry is Industry.INSURANCE:
        col = f"{prefix}state_name"
        return (
            "CASE "
            f"WHEN lower({col}) IN ({_sql_lower_list(NORTH_STATE_NAMES)}) THEN 'North' "
            f"WHEN lower({col}) IN ({_sql_lower_list(SOUTH_STATE_NAMES)}) THEN 'South' "
            f"WHEN lower({col}) IN ({_sql_lower_list(EAST_STATE_NAMES)}) THEN 'East' "
            "ELSE 'West' END"
        )
    col = f"{prefix}state_code"
    north = ", ".join(f"'{c}'" for c in sorted(NORTH_STATES))
    south = ", ".join(f"'{c}'" for c in sorted(SOUTH_STATES))
    east = ", ".join(f"'{c}'" for c in sorted(EAST_STATES))
    return (
        "CASE "
        f"WHEN {col} IN ({north}) THEN 'North' "
        f"WHEN {col} IN ({south}) THEN 'South' "
        f"WHEN {col} IN ({east}) THEN 'East' "
        "ELSE 'West' END"
    )


def _sql_lower_list(names: frozenset[str]) -> str:
    return ", ".join(f"'{n}'" for n in sorted(names))


def mentioned_zones(question: str) -> tuple[str, ...]:
    found: list[str] = []
    for match in _ZONE_WORD.finditer(question or ""):
        zone = match.group(1).title()
        if zone in _ZONE_SET and zone not in found:
            found.append(zone)
    return tuple(found)


def forbidden_zones(question: str, scope: RegionScope) -> tuple[str, ...]:
    if scope.unrestricted:
        return ()
    return tuple(z for z in mentioned_zones(question) if z not in scope.zones)


async def load_region_scope(session: AsyncSession, user: User) -> RegionScope:
    if user.role is Role.ADMIN:
        return RegionScope.all_regions(user)
    rows = (
        (
            await session.execute(
                select(UserRegionAccess.region_id).where(UserRegionAccess.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    zones = tuple(z for z in ZONES if any(_canonical_zone(r) == z for r in rows))
    if not zones:
        # Legacy accounts (e.g. user1) with no mapping keep full access.
        return RegionScope.all_regions(user)
    return RegionScope(unrestricted=False, zones=zones, user_id=user.id, username=user.username)


def apply_region_sql(sql: str, industry: Industry, scope: RegionScope) -> str:
    if not scope.restricted or not sql or not sql.strip():
        return sql
    stripped = sql.strip()
    if re.match(r"^(SET|SHOW|RESET)\b", stripped, re.I):
        return sql
    explain = re.match(r"^(EXPLAIN(?:\s+ANALYZE)?)\s+", stripped, re.I)
    body = stripped[explain.end() :] if explain else stripped
    rewritten = _rewrite_tables(body, industry, scope)
    if explain:
        return f"{explain.group(1)} {rewritten}"
    return rewritten


def _rewrite_tables(sql: str, industry: Industry, scope: RegionScope) -> str:
    counter = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal counter
        kind, table, alias = match.group(1), match.group(2), match.group(3)
        window_start = max(0, match.start() - 12)
        if "/*rls*/" in sql[window_start : match.end()]:
            return match.group(0)
        wrapped = _scoped_subquery(table.lower(), industry, scope)
        if alias and alias.upper() not in _SQL_KEYWORDS:
            return f"{kind} {wrapped} {alias}"
        counter += 1
        return f"{kind} {wrapped} _rls_{counter}"

    return _TABLE_RE.sub(repl, sql)


def _scoped_subquery(table: str, industry: Industry, scope: RegionScope) -> str:
    dim = "insurance.dim_region" if table.startswith("insurance.") else "automotive.dim_region"
    ind = Industry.INSURANCE if table.startswith("insurance.") else industry
    if table in _DIM_REGION:
        pred = scope.dim_predicate(ind)
        return f"(SELECT * FROM {table} WHERE {pred}) /*rls*/"
    pred = f"region_id IN (SELECT region_id FROM {dim} WHERE {scope.dim_predicate(ind)})"
    return f"(SELECT * FROM {table} WHERE {pred}) /*rls*/"


class RegionScopedConnection:
    """Forwards to an analytics connection after rewriting region-bearing SQL."""

    def __init__(self, inner: AsyncConnection, industry: Industry, scope: RegionScope) -> None:
        self._inner = inner
        self._industry = industry
        self._scope = scope

    async def execute(self, statement: Any, parameters: Any = None, **kwargs: Any) -> Any:
        if isinstance(statement, TextClause):
            rewritten = apply_region_sql(statement.text, self._industry, self._scope)
            if rewritten != statement.text:
                statement = sql_text(rewritten)
        elif isinstance(statement, str):
            statement = sql_text(apply_region_sql(statement, self._industry, self._scope))
        return await self._inner.execute(statement, parameters, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def assert_requested_region(scope: RegionScope, requested: str | None) -> None:
    """Reject a client-supplied region/zone that the caller cannot see."""
    if not requested or scope.unrestricted:
        return
    if not scope.allows_label(requested):
        raise RegionAccessDeniedError(
            scope.deny_message(requested), details={"attempted": requested}
        )


async def deny_if_out_of_scope(
    session: AsyncSession,
    scope: RegionScope,
    *,
    attempted: str,
    action: str,
) -> None:
    if scope.unrestricted:
        return
    details = (
        f"{scope.username or 'user'} attempted access to {attempted} "
        f"(allowed: {', '.join(scope.zones)}; action: {action})"
    )
    logger.info("region_access_denied %s", details)
    try:
        await record_admin_action(session, scope.user_id, AdminAction.REGION_ACCESS_DENIED, details)
        await session.commit()
    except Exception:
        logger.warning("Could not persist region-access audit row", exc_info=True)
        try:
            await session.rollback()
        except Exception:
            logger.debug("Rollback after region-access audit failure also failed", exc_info=True)
    raise RegionAccessDeniedError(scope.deny_message(attempted), details={"attempted": attempted})
