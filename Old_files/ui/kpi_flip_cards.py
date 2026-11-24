"""
ui/kpi_flip_cards.py
Flip / explainable KPI cards for BI-style transparency.
"""
from __future__ import annotations

import html
import re
from typing import Any


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _slug(label: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9]+", "-", (label or "kpi").strip().lower()).strip("-")
    return raw[:48] or "kpi"


def flip_kpi_card_html(
    *,
    label: str,
    value: str,
    accent: str = "revenue",
    sub: str = "Hover or click to explain",
    source_columns: str | list[str] | None = None,
    aggregation: str | None = None,
    records_count: Any = None,
    records_label: str = "Records",
    filters: str = "None",
    formula: str | None = None,
    business_logic: str | None = None,
    delay: float = 0.0,
    featured: bool = False,
    card_id: str | None = None,
) -> str:
    """
    Front: label + value. Back: calculation transparency.
    Hover flips on desktop; click/tap toggles via checkbox (stays flipped).
    """
    cid = card_id or f"kpi-flip-{_slug(label)}"
    if isinstance(source_columns, (list, tuple)):
        source_txt = ", ".join(str(c) for c in source_columns if c) or "—"
    else:
        source_txt = str(source_columns or "—")

    rows: list[tuple[str, str]] = []
    if formula:
        rows.append(("Formula", formula))
        if source_columns:
            rows.append(("Source columns", source_txt))
        if business_logic:
            rows.append(("Business logic", business_logic))
    else:
        rows.append(("Source column", source_txt))
        if aggregation:
            rows.append(("Aggregation", aggregation))
        if business_logic:
            rows.append(("Business logic", business_logic))

    if records_count is not None and str(records_count) != "":
        try:
            n = int(float(records_count))
            rec_txt = f"{n:,}"
        except Exception:
            rec_txt = str(records_count)
        rows.append((records_label, rec_txt))
    rows.append(("Applied filters", filters or "None"))

    detail_rows = "".join(
        f'<div class="kpi-flip-row">'
        f'<span class="kpi-flip-k">{_esc(k)}</span>'
        f'<span class="kpi-flip-v">{_esc(v)}</span>'
        f"</div>"
        for k, v in rows
    )
    feat = " kpi-featured" if featured else ""
    return f"""
<div class="kpi-flip-wrap kpi-anim" style="animation-delay:{delay:.2f}s">
  <input type="checkbox" class="kpi-flip-toggle" id="{_esc(cid)}" />
  <label class="kpi-flip accent-{_esc(accent)}{feat}" for="{_esc(cid)}" tabindex="0">
    <div class="kpi-flip-inner">
      <div class="kpi-flip-face kpi-flip-front">
        <div class="kpi-accent"></div>
        <div class="kpi-flip-hint">Explain</div>
        <div class="kv">{_esc(value)}</div>
        <div class="kl">{_esc(label)}</div>
        <div class="ks">{_esc(sub)}</div>
      </div>
      <div class="kpi-flip-face kpi-flip-back">
        <div class="kpi-accent"></div>
        <div class="kpi-flip-back-title">{_esc(label)}</div>
        <div class="kpi-flip-details">{detail_rows}</div>
        <div class="kpi-flip-back-foot">Click again to return</div>
      </div>
    </div>
  </label>
</div>
""".strip()


def render_flip_kpi_grid(
    cards: list[dict[str, Any]],
    *,
    columns: int = 5,
) -> str:
    """Return HTML for a responsive flip-card grid."""
    cols = max(1, min(int(columns), 5))
    items = []
    for i, card in enumerate(cards):
        items.append(
            flip_kpi_card_html(
                label=card.get("label") or "KPI",
                value=card.get("value") or "—",
                accent=card.get("accent") or "revenue",
                sub=card.get("sub") or "Hover or click to explain",
                source_columns=card.get("source_columns"),
                aggregation=card.get("aggregation"),
                records_count=card.get("records_count"),
                records_label=card.get("records_label") or "Records",
                filters=card.get("filters") or "None",
                formula=card.get("formula"),
                business_logic=card.get("business_logic"),
                delay=i * 0.04,
                featured=bool(card.get("featured")),
                card_id=card.get("card_id") or f"kpi-flip-{i}-{_slug(str(card.get('label') or i))}",
            )
        )
    return (
        f'<div class="kpi-flip-grid" style="--kpi-cols:{cols}">'
        + "".join(items)
        + "</div>"
    )
