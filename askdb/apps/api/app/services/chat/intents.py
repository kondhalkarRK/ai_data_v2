"""Pure intent classifiers used by chat orchestration."""

from __future__ import annotations

import re

from app.core.config import Industry
from app.core.constants import FOLLOWUP_TRIGGER_TOKENS, MAX_FOLLOWUP_QUESTION_WORDS

_VAGUE = {"show me", "report", "dashboard", "metrics", "data", "insights", "analysis"}
_SURPRISE = re.compile(
    r"\b(surprise\s+me|random\s+(?:insight|fact)|something\s+interesting|"
    r"interesting\s+(?:insight|fact))\b",
    re.IGNORECASE,
)
_WHATIF = re.compile(
    r"\b(what[\s-]*if|scenario|increase(?:d|s)?|decrease(?:d|s)?|raise|lower|"
    r"grow|reduce|up\s+by|down\s+by)\b",
    re.IGNORECASE,
)
_UNSAFE_OR_UNRELATED = re.compile(
    r"\b(weather|forecast temperature|football|soccer|cricket|basketball|"
    r"election|politics|president|prime minister|crypto(?:currency)?|bitcoin|"
    r"ethereum|recipe|cooking|bake|movie|celebrity|"
    r"ignore (?:all |the )?(?:previous|prior|system) instructions?|"
    r"reveal (?:the )?(?:system prompt|secrets?|passwords?|api keys?)|"
    r"drop\s+table|delete\s+from|truncate\s+table|grant\s+|"
    r"alter\s+table|insert\s+into|update\s+\w+\s+set)\b",
    re.IGNORECASE,
)


def _normalized(question: str) -> str:
    return re.sub(r"\s+", " ", (question or "").strip().lower()).strip(" ?!.")


def is_followup(question: str) -> bool:
    """Return whether a short question appears to modify a prior request."""
    q = _normalized(question)
    if not q or len(q.split()) > MAX_FOLLOWUP_QUESTION_WORDS:
        return False
    return any(q == token or q.startswith(f"{token} ") for token in FOLLOWUP_TRIGGER_TOKENS)


def needs_clarification(question: str) -> str | None:
    """Return a clarification prompt for requests without a usable entity."""
    q = _normalized(question)
    if not q or q in _VAGUE or len(re.findall(r"\w+", q)) < 2:
        return (
            "What business metric or entity should I analyze "
            "(for example, claims, premium, revenue, models, or dealers)?"
        )
    return None


def is_out_of_bounds(question: str, industry: Industry) -> bool:
    """Identify clearly unrelated or instruction-injection requests."""
    del industry  # Reserved for industry-specific policies.
    return bool(_UNSAFE_OR_UNRELATED.search(question or ""))


def is_surprise_me(question: str) -> bool:
    return bool(_SURPRISE.search(question or ""))


def is_whatif(question: str) -> bool:
    return bool(_WHATIF.search(question or ""))


def parse_whatif(question: str) -> dict[str, object] | None:
    """Parse a simple directional scenario into a stable payload."""
    if not is_whatif(question):
        return None
    q = _normalized(question)
    amount = re.search(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<percent>%|percent)?", q)
    if amount is None:
        return None
    direction = (
        "down"
        if re.search(r"\b(decrease(?:d|s)?|lower|reduce[sd]?|down)\b", q)
        else "up"
    )
    metric_match = re.search(
        r"(?:what[\s-]*if\s+)?(?P<metric>[a-z][a-z\s_-]*?)\s+"
        r"(?:increase(?:d|s)?|decrease(?:d|s)?|raise|lower|grow|reduce|up|down)",
        q,
    )
    result: dict[str, object] = {
        "change_type": "percent" if amount.group("percent") else "absolute",
        "change_value": float(amount.group("value")),
        "direction": direction,
    }
    if metric_match:
        metric = metric_match.group("metric").strip(" _-")
        if metric and metric != "scenario":
            result["metric"] = metric
    return result


def suggested_followups(industry: Industry, path: str) -> list[str]:
    """Return three concise, governed follow-up chips."""
    if industry is Industry.INSURANCE:
        choices = [
            "Break this down by region",
            "Show the monthly trend",
            "Compare claim count and premium",
        ]
    else:
        choices = [
            "Break this down by dealer",
            "Show the monthly trend",
            "Compare the top models",
        ]
    if path == "out_of_bounds":
        return (
            ["Show loss ratio", "Show claims by status", "Show premium by month"]
            if industry is Industry.INSURANCE
            else ["Show revenue by month", "Show top models", "Show EV share"]
        )
    return choices
