"""Rule-based message classifier (no LLM). Single entry before plan_turn after region guard."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from app.core.config import Industry
from app.services.chat.intents import is_out_of_bounds
from app.services.chat.query_router import DOCUMENT_CUES

logger = logging.getLogger(__name__)

_LIVE_EXTERNAL = re.compile(
    r"\b(weather|forecast|temperature|cricket|football|soccer|basketball|"
    r"election|bitcoin|ethereum|crypto(?:currency)?|stock\s+price|"
    r"match\s+yesterday|won the\s+\w+\s+match)\b",
    re.I,
)

_GREETING = re.compile(
    r"^(?:hi(?: there)?|hello|hey|good\s+(?:morning|afternoon|evening)|howdy)\b",
    re.I,
)
_THANKS = re.compile(
    r"^(?:thanks(?: a lot| so much)?|thank you|thx|appreciate it)\b",
    re.I,
)
_JOKE = re.compile(r"\b(tell me a joke|make me laugh|say something funny)\b", re.I)
_NON_DATA_CHITCHAT = re.compile(
    r"\b(dinner|lunch|brunch|weekend plans|movie tonight|vacation plans)\b",
    re.I,
)

# Programming / developer-help cues. Deliberately excludes "sql": SQL-shaped asks are routed
# to the governed NLQ path, never to open-ended code help.
_OFF_TOPIC_PROGRAMMING = re.compile(
    r"\b(python|javascript|typescript|golang|java|php|django|flask|node\.?js|reactjs|"
    r"kubernetes|dockerfile|regex|leetcode|stack\s*overflow|linked\s+list|"
    r"write\s+(?:me\s+)?(?:an?\s+)?(?:function|script|program|code)|"
    r"debug\s+(?:my|this)\s+code|code\s+snippet)\b",
    re.I,
)

_UNSUPPORTED = re.compile(
    r"\b("
    r"delete\s+(?:all|from)|drop\s+table|truncate\s+table|"
    r"other users['\u2019]?|someone else['\u2019]s|"
    r"chat history|"
    r"ignore (?:all |the |your )?(?:previous |prior |system )?instructions?|"
    r"reveal (?:the )?(?:system prompt|secrets?|passwords?|api keys?)"
    r")\b",
    re.I,
)

_APP_REFERENCE = r"(?:in\s+)?(?:this\s+(?:app|product|tool|workspace)|ask\s*(?:db|me)|the\s+semantic\s+layer|here|(?:insurance|automotive)\s+mode)"
_APP_HELP = re.compile(
    r"("
    r"\bhow\s+do\s+i\s+ask\b"
    r"|\bwhat\s+(?:tables|metrics|kpis?|measures|dimensions)\b.*\b(?:can\s+i|available|are\s+there)\b"
    r"|\bwhich\s+(?:tables|metrics|kpis?|measures|dimensions|regions)\b.*\b(?:can\s+i|available|are\s+in|in\s+the\s+semantic)\b"
    rf"|\bwhat\s+does\s+.+\bmean\b.*{_APP_REFERENCE}"
    rf"|\bdifference\s+between\b.+{_APP_REFERENCE}"
    rf"|\bhow\s+is\s+.+\bcalculated\b.*{_APP_REFERENCE}"
    r"|^what(?:'s|\s+is)\s+an?\s+(?:kpi|metric|measure|dimension)\s*\??$"
    r")",
    re.I,
)

_KNOWLEDGE_OPENER = re.compile(
    r"^(?:explain|what(?:'s|\s+is|\s+are)\s+(?:the\s+)?|who\s+(?:is|was|were)|"
    r"where\s+is|when\s+(?:did|was)|how\s+does)\b",
    re.I,
)
_DATA_CUES = re.compile(
    r"\b(our|my|we|us|show|list|compare|trend|top|bottom|by\s+\w+|last\s+(?:month|quarter|year)|"
    r"this\s+(?:month|quarter|year)|total|count|average|sum|growth|share)\b",
    re.I,
)


class MessageRoute(StrEnum):
    PASSTHROUGH = "passthrough"
    GENERAL_CHAT = "general_chat"
    UNSUPPORTED = "unsupported"
    OUT_OF_SCOPE_LIVE = "out_of_scope_live"
    APP_HELP = "app_help"
    DOCUMENT_QUERY = "document_query"
    GENERAL_KNOWLEDGE = "general_knowledge"


@dataclass(frozen=True, slots=True)
class MessageClassification:
    route: MessageRoute
    reason: str
    applied: bool = True


_NON_ANALYTIC_ROUTES = frozenset(
    {
        MessageRoute.GENERAL_CHAT,
        MessageRoute.UNSUPPORTED,
        MessageRoute.OUT_OF_SCOPE_LIVE,
        MessageRoute.APP_HELP,
        MessageRoute.DOCUMENT_QUERY,
        MessageRoute.GENERAL_KNOWLEDGE,
    }
)


def rule_route_interrupts_analytical_context(question: str, industry: Industry) -> bool:
    """True when rules classify the message as non-analytic (greeting, chitchat, etc.)."""
    decision = classify_message(question, industry, enabled=True)
    return decision.route in _NON_ANALYTIC_ROUTES


def classify_message(
    question: str,
    industry: Industry,
    *,
    enabled: bool,
    data_vocabulary: Callable[[str], bool] | None = None,
) -> MessageClassification:
    """Classify a message by rules. When disabled, shadow-log and return PASSTHROUGH.

    ``data_vocabulary`` reports whether the text names anything in the governed
    vocabulary; GENERAL_KNOWLEDGE is only possible when it is supplied and says no.
    """
    text = (question or "").strip()
    try:
        decision = _rule_classify(text, industry, data_vocabulary)
    except Exception:
        logger.exception("message_classifier failed; passthrough")
        return MessageClassification(MessageRoute.PASSTHROUGH, "classifier_error", applied=enabled)
    if not enabled:
        logger.info(
            "message_classifier shadow route=%s reason=%s text=%r",
            decision.route.value,
            decision.reason,
            text[:120],
        )
        return MessageClassification(MessageRoute.PASSTHROUGH, "router_disabled", applied=False)
    return decision


def _rule_classify(
    text: str,
    industry: Industry,
    data_vocabulary: Callable[[str], bool] | None,
) -> MessageClassification:
    q = re.sub(r"\s+", " ", text).strip()
    ql = q.lower()
    if not q:
        return MessageClassification(MessageRoute.PASSTHROUGH, "empty")
    if _LIVE_EXTERNAL.search(q):
        return MessageClassification(MessageRoute.OUT_OF_SCOPE_LIVE, "live_external_cue")
    if _UNSUPPORTED.search(q) or is_out_of_bounds(q, industry):
        return MessageClassification(MessageRoute.UNSUPPORTED, "unsafe_or_unsupported")
    if len(q.split()) <= 6 and _THANKS.match(ql):
        return MessageClassification(MessageRoute.GENERAL_CHAT, "thanks")
    if len(q.split()) <= 6 and _GREETING.match(ql):
        return MessageClassification(MessageRoute.GENERAL_CHAT, "greeting")
    if _JOKE.search(q):
        return MessageClassification(MessageRoute.GENERAL_CHAT, "joke_request")
    if _NON_DATA_CHITCHAT.search(q):
        return MessageClassification(MessageRoute.GENERAL_CHAT, "non_data_chitchat")
    if _OFF_TOPIC_PROGRAMMING.search(q):
        return MessageClassification(MessageRoute.GENERAL_KNOWLEDGE, "off_topic_programming")
    if _APP_HELP.search(q):
        return MessageClassification(MessageRoute.APP_HELP, "app_help_phrasing")
    if any(cue in ql for cue in DOCUMENT_CUES):
        return MessageClassification(MessageRoute.DOCUMENT_QUERY, "document_phrasing")
    if (
        data_vocabulary is not None
        and _KNOWLEDGE_OPENER.match(q)
        and not _DATA_CUES.search(q)
        and not data_vocabulary(q)
    ):
        return MessageClassification(MessageRoute.GENERAL_KNOWLEDGE, "general_knowledge_phrasing")
    return MessageClassification(MessageRoute.PASSTHROUGH, "analytic_or_unknown")


def template_general_chat(reason: str) -> str:
    if reason == "joke_request":
        return "I keep my jokes for quiet days — ask me about revenue, units, or claims in your data."
    if reason == "thanks":
        return "You're welcome. Ask another analytics question whenever you like."
    if reason == "greeting":
        return "Hello! Ask me a governed analytics question about your industry data."
    return "Happy to chat briefly, but I'm best at governed analytics questions about your data."


def template_scope_declined(industry: Industry) -> str:
    examples = (
        "claims by status or premium by month"
        if industry is Industry.INSURANCE
        else "units sold by state or revenue by month"
    )
    return (
        "Ask Me is built for your business data and analytics, so I can't help with general "
        "knowledge or programming questions. I'm happy to help with something like "
        f"\u201c{examples}\u201d."
    )


def template_unsupported() -> str:
    return (
        "I can't help with that request. I only answer governed analytics questions "
        "within your permissions."
    )


def template_out_of_scope_live() -> str:
    return (
        "I can't access live or external information (weather, markets, sports, and so on). "
        "Ask about metrics in your governed dataset instead."
    )
