"""Spell correction for business vocabulary before planning.

Only words from a closed business vocabulary are corrected ("revnue" -> revenue,
"salse" -> sales, "quartely" -> quarterly). Business values (brands, cities,
states) are corrected later by the entity resolver, which knows the live
catalog and reports what it interpreted. Unknown words that are not close to a
vocabulary word are left alone so the resolver can ask about them.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

_VOCABULARY: tuple[str, ...] = tuple(
    """
    revenue sales sale sold selling sell units unit orders order quantity volume turnover
    price average total count number amount value growth trend trends compare comparison
    versus between share market contribution percentage percent ratio running cumulative
    moving rolling ranking rank ranked highest lowest largest smallest bottom fastest slowest
    growing declining increasing decreasing performance performing breakdown distribution
    brand brands make makes manufacturer model models vehicle vehicles segment segments
    dealer dealers dealership salesperson salespeople region regions city cities state
    states location colour colours color colors fuel engine electric petrol diesel hybrid
    hatchback sedan month months monthly quarter quarters quarterly year years yearly
    annual week weekly daily previous current latest financial fiscal
    premium premiums written earned claims claim incurred paid severity frequency loss
    policy policies product products agent agents broker brokers channel channels branch
    branches coverage tier tiers renewal renewals approval approved rejected status
    customers customer insurance motor health comprehensive exposure reported settled
    """.split()  # noqa: SIM905
)
# Everyday words one edit away from a vocabulary word ("made" / make, "tier" / tie).
_COMMON = frozenset(
    """
    made mode more many much some same sell till time rate also over ever even each when
    then than them they there their where were will with what have from into onto upon
    shown show kept keep like line lines list most must name next once ones part past
    plus rest rise rose seen sets size sort such sure take tell test that this those
    true type used user very want well went whom whose wide word work zero
    """.split()  # noqa: SIM905
)
_PHRASES: tuple[tuple[str, str], ...] = (
    (r"\blose\s+ratio\b", "loss ratio"),
    (r"\bloose\s+ratio\b", "loss ratio"),
    (r"\bmarket\s+shair\b", "market share"),
    (r"\bsale's\b", "sales"),
    (r"\byear\s+on\s+year\b", "year over year"),
    (r"\bmonth\s+on\s+month\b", "month over month"),
)
_WORD = re.compile(r"[A-Za-z]+")


@dataclass(slots=True)
class SpellResult:
    text: str
    corrections: list[tuple[str, str]] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.corrections)

    def notes(self) -> list[str]:
        return [f"Read \u201c{wrong}\u201d as \u201c{right}\u201d." for wrong, right in self.corrections]


def edit_distance(a: str, b: str) -> int:
    """Optimal string alignment distance (Levenshtein plus adjacent transpositions)."""
    if a == b:
        return 0
    rows = len(a) + 1
    cols = len(b) + 1
    d = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        d[i][0] = i
    for j in range(cols):
        d[0][j] = j
    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def _allowed_distance(word: str) -> int:
    if len(word) < 4:
        return 0
    return 1 if len(word) <= 6 else 2


def _closest(word: str, vocabulary: Iterable[str]) -> str | None:
    limit = _allowed_distance(word)
    if not limit:
        return None
    best: list[tuple[int, int, str]] = []
    for target in vocabulary:
        if target[0] != word[0] or abs(len(target) - len(word)) > limit:
            continue
        distance = edit_distance(word, target)
        if distance <= limit:
            best.append((distance, abs(len(target) - len(word)), target))
    if not best:
        return None
    best.sort()
    if len(best) > 1 and best[0][:2] == best[1][:2]:
        return None
    return best[0][2]


def correct_question(question: str, *, protected: Iterable[str] = ()) -> SpellResult:
    """Fix misspelled business words; ``protected`` words (catalog values) are never touched."""
    text = question or ""
    corrections: list[tuple[str, str]] = []
    for pattern, replacement in _PHRASES:
        found = re.search(pattern, text, re.I)
        if found and found.group(0).casefold() != replacement:
            corrections.append((found.group(0), replacement))
            text = re.sub(pattern, replacement, text, flags=re.I)
    known = set(_VOCABULARY) | _COMMON | {word.casefold() for word in protected}
    seen: dict[str, str | None] = {}
    pieces: list[str] = []
    last = 0
    for found in _WORD.finditer(text):
        word = found.group(0)
        lowered = word.casefold()
        if (
            lowered in known
            or lowered.removesuffix("s") in known
            or lowered.removesuffix("es") in known
            or f"{lowered}s" in known
        ):
            continue
        if lowered not in seen:
            seen[lowered] = _closest(lowered, _VOCABULARY)
        fixed = seen[lowered]
        if fixed is None:
            continue
        pieces.append(text[last : found.start()])
        pieces.append(fixed)
        last = found.end()
        if (word, fixed) not in corrections:
            corrections.append((word, fixed))
    pieces.append(text[last:])
    return SpellResult("".join(pieces), corrections)
