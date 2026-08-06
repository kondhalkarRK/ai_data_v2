# features/okf_knowledge/okf_answer.py
#
# Knowledge-first answers from OKF SOPs + light data checks.
# Used when users ask policy / demand / interpretation questions
# (e.g. "is EV demand increasing?") instead of pure SQL listings.

from __future__ import annotations

from typing import Any

import pandas as pd

# call_llm imported lazily inside answer path (avoids hard streamlit import at module load)

# Bump when packaged OKF docs change — triggers auto-seed refresh
_OKF_CONTENT_VERSION = "pv-ops-okf-v3-2026-08"

_KNOWLEDGE_HINTS = (
    # EV / reporting SOPs
    "ev demand", "electric demand", "are ev", "is ev", "evs taking",
    "taking off", "demand increas", "demand grow", "powertrain report",
    "how should we report", "how do we report", "according to sop",
    "according to the sop", "business policy", "playbook",
    "why were 2020", "why was 2020", "covid", "lockdown",
    "narrative standard", "how should i narrate",
    # Handbooks & dealer ops
    "handbook", "dealer manual", "handover checklist", "booking recognition",
    "when does a sale count", "dealer ops", "dealer operation",
    "lead response", "stock ageing", "aged stock",
    # Regional targets
    "regional target", "zone target", "sales target", "unit target",
    "fy2026 target", "fy 2026", "on track for north", "on track for south",
    "what is the east target", "what is our target", "mbR target",
    "ev share target", "growth target",
    # Strategy
    "growth strategy", "strategic plan", "strategy plan", "annual plan",
    "our strategy", "competitive response", "festive discount", "ev strategy",
    "why focus on metro", "pillar", "risk register",
    # General policy (not in data)
    "company policy", "operating procedure", "escalation threshold",
    "what should we do", "business guidance", "according to handbook",
)

_ANALYTICAL_ONLY = (
    "show ", "display ", "list ", "top ", "bottom ", "how many ",
    "total ", "compare ", " trend", " by make", " by region", " by month",
    " by colour", " by color", " by model", " by year", "group by",
    "drill down", "drill into", "break down", "break that down",
    "slice by", "split by", "zoom in",
)

_DRILL_FOLLOWUP_SIGNALS = (
    "drill down", "drill into", "break down", "break that down",
    "slice by", "split by", "zoom in", "same but", "same for",
    "what about", "how about", "now for", "only for", "and for",
    "filter to", "just for", "for tata", "for maruti",
)


def _is_data_drill_or_followup(question: str) -> bool:
    """Drill-down / follow-up analytics must stay on SQL path, not OKF docs."""
    q = (question or "").lower().strip()
    if not q:
        return False
    if any(s in q for s in _DRILL_FOLLOWUP_SIGNALS):
        return True
    try:
        from core.conversation_state import detect_followup, get_sql_anchor, should_use_anchor
        if detect_followup(question):
            return True
        if get_sql_anchor() and should_use_anchor(question):
            return True
    except Exception:
        pass
    return False

_POLICY_SIGNALS = (
    "target", "strategy", "handbook", "policy", "sop", "plan", "threshold",
    "escalation", "should we", "how should", "how do we", "what is our",
    "dealer", "operating", "mbR", "guidance", "procedure", "pillar",
)

_OKF_DOC_TYPES = frozenset({
    "sop", "guide", "handbook", "regional_targets", "strategy_plan",
})

_EV_DEMAND_HINTS = (
    "ev demand", "electric demand", "are ev", "is ev",
    "evs taking", "taking off", "electric vehicle demand",
    "ev share", "ev growth", "electric sales grow",
)


def ensure_okf_ready(force: bool = False) -> dict:
    """Lazy-seed packaged SOPs into OKF + Chroma if empty or content version changed."""
    try:
        from features.okf_knowledge.okf_retriever import indexed_concept_count, reindex_all
        from features.okf_knowledge.okf_bootstrap import bootstrap_business_knowledge
        from features.okf_knowledge.okf_store import list_bundles
        import os

        ver_path = os.path.join("rag_storage", "okf_bundles", ".content_version")
        disk_ver = ""
        if os.path.isfile(ver_path):
            try:
                with open(ver_path, encoding="utf-8") as f:
                    disk_ver = f.read().strip()
            except Exception:
                disk_ver = ""

        count = indexed_concept_count()
        bundles = list_bundles()
        needs_refresh = (
            force
            or count == 0
            or not bundles
            or disk_ver != _OKF_CONTENT_VERSION
        )
        if needs_refresh:
            summary = bootstrap_business_knowledge(
                force=True if (disk_ver and disk_ver != _OKF_CONTENT_VERSION) or force else False
            )
            # If skip-path left empty index, force full bootstrap
            if indexed_concept_count() == 0 or disk_ver != _OKF_CONTENT_VERSION:
                summary = bootstrap_business_knowledge(force=True)
            if indexed_concept_count() == 0:
                reindex_all()
            os.makedirs(os.path.dirname(ver_path), exist_ok=True)
            with open(ver_path, "w", encoding="utf-8") as f:
                f.write(_OKF_CONTENT_VERSION)
            summary["indexed"] = indexed_concept_count()
            summary["content_version"] = _OKF_CONTENT_VERSION
            return summary
        return {
            "docs": len(bundles),
            "concepts": 0,
            "indexed": count,
            "skipped": True,
            "content_version": _OKF_CONTENT_VERSION,
        }
    except Exception as e:
        return {"docs": 0, "concepts": 0, "indexed": 0, "error": str(e)}


def _is_analytical_data_question(question: str) -> bool:
    """True when the user clearly wants a SQL/table answer, not a policy doc."""
    q = (question or "").lower().strip()
    if not q:
        return False
    has_analytical = any(t in q for t in _ANALYTICAL_ONLY)
    has_policy = any(p in q for p in _POLICY_SIGNALS)
    return has_analytical and not has_policy


def _okf_retrieval_hit(question: str, min_snippets: int = 1) -> bool:
    """True when OKF embeddings find relevant business-doc snippets."""
    try:
        from features.okf_knowledge.okf_retriever import get_relevant_snippets
        snippets = get_relevant_snippets(question, top_k=3, max_context_chars=500)
        if len(snippets) < min_snippets:
            return False
        return any(
            (s.get("doc_type") or "sop") in _OKF_DOC_TYPES
            for s in snippets
        )
    except Exception:
        return False


def is_knowledge_question(question: str) -> bool:
    """
    Route to OKF when the question needs business documents — not the glossary.

    Answers from handbooks, regional targets, strategy plans, and SOPs when
    the ask is policy/interpretation. Pure analytics (show X by Y) stay on NLQ.
    """
    try:
        from features.okf_knowledge.target_alignment import is_target_alignment_question
        if is_target_alignment_question(question):
            return True
    except Exception:
        pass

    q = (question or "").lower().strip()
    if not q:
        return False

    # Follow-up drill-downs (e.g. "drill down for Tata by model") are data queries
    if _is_data_drill_or_followup(question):
        return False

    if any(h in q for h in _KNOWLEDGE_HINTS):
        return True

    if any(p in q for p in _POLICY_SIGNALS):
        return True

    # Clear data query — let semantic NLQ handle (glossary + SQL)
    if _is_analytical_data_question(q):
        return False

    # Non-analytical question with strong OKF document match
    try:
        ensure_okf_ready()
        if _okf_retrieval_hit(q):
            return True
    except Exception:
        pass

    return False


def is_ev_demand_question(question: str) -> bool:
    q = (question or "").lower().strip()
    if not q:
        return False
    if any(h in q for h in _EV_DEMAND_HINTS):
        return True
    # typo-tolerant: "increse", "incrase"
    if "ev" in q and any(w in q for w in ("demand", "increas", "grow", "rising", "up")):
        return True
    if "electric" in q and any(w in q for w in ("demand", "increas", "grow", "share")):
        return True
    return False


def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower = {str(c).lower(): c for c in df.columns}
    for cand in candidates:
        if cand in lower:
            return lower[cand]
    for cand in candidates:
        for k, v in lower.items():
            if cand in k:
                return v
    return None


def compute_ev_share_by_year(df: pd.DataFrame) -> pd.DataFrame | None:
    """EV unit share by calendar year (SOP-003 certified formula)."""
    if df is None or df.empty:
        return None
    eng = _find_col(df, ["engine_type", "enginetype", "powertrain"])
    qty = _find_col(df, ["order_qty", "qty", "quantity", "units"])
    date = _find_col(df, ["sales_date", "sale_date", "order_date", "date"])
    if not eng or not qty or not date:
        return None
    tmp = df[[eng, qty, date]].copy()
    tmp["__year__"] = pd.to_datetime(tmp[date], errors="coerce").dt.year
    tmp[qty] = pd.to_numeric(tmp[qty], errors="coerce")
    tmp = tmp.dropna(subset=["__year__", qty, eng])
    if tmp.empty:
        return None

    rows = []
    for year, g in tmp.groupby("__year__", sort=True):
        total = float(g[qty].sum())
        ev = float(g.loc[g[eng].astype(str).str.lower().eq("electric"), qty].sum())
        share = (ev / total * 100.0) if total else 0.0
        rows.append({
            "year": int(year),
            "ev_units": int(round(ev)),
            "total_units": int(round(total)),
            "ev_share_pct": round(share, 2),
        })
    out = pd.DataFrame(rows)
    return out if not out.empty else None


def _trend_summary(share_df: pd.DataFrame) -> tuple[str, list[str]]:
    years = share_df["year"].astype(int).tolist()
    shares = share_df["ev_share_pct"].astype(float).tolist()
    first_y, last_y = years[0], years[-1]
    first_s, last_s = shares[0], shares[-1]
    # Prefer last complete-ish vs early baseline
    rising = last_s > first_s * 1.5 or (last_s - first_s) >= 3.0
    headline = (
        f"Yes — EV demand is rising: unit share moved from {first_s:.1f}% in {first_y} "
        f"to {last_s:.1f}% in {last_y}."
        if rising
        else f"EV share is {last_s:.1f}% in {last_y} (vs {first_s:.1f}% in {first_y})."
    )
    findings = [
        f"EV units in {last_y}: {int(share_df.iloc[-1]['ev_units']):,} "
        f"of {int(share_df.iloc[-1]['total_units']):,} total units.",
        "Share is measured as SUM(order_qty WHERE engine_type='Electric') / SUM(order_qty).",
        "Petrol/ICE still leads absolute volume — rising EV share ≠ ICE collapse.",
    ]
    return headline, findings


def answer_knowledge_question(
    question: str,
    working_df: pd.DataFrame | None = None,
) -> dict[str, Any] | None:
    """
    Build a knowledge-backed answer.

    Returns dict suitable for chat/query message data, or None if OKF
    has nothing useful and no EV table can be built.
    """
    ensure_okf_ready()

    # Target vs actual (data + IND-PV-REG-001) — before generic OKF text path
    try:
        from features.okf_knowledge.target_alignment import (
            is_target_alignment_question,
            compute_target_alignment,
            build_alignment_sql,
        )
        from features.okf_knowledge.target_narration import generate_target_alignment_narration

        if is_target_alignment_question(question) and working_df is not None:
            alignment = compute_target_alignment(question, working_df)
            if alignment:
                snippets: list[dict] = []
                try:
                    from features.okf_knowledge.okf_retriever import get_relevant_snippets
                    snippets = get_relevant_snippets(
                        "IND-PV-REG-001 regional sales targets FY2026 escalation",
                        top_k=2,
                        max_context_chars=600,
                    )
                except Exception:
                    snippets = []
                citations = [
                    {
                        "title": s.get("title"),
                        "source_doc": s.get("source_doc"),
                        "source_page": s.get("source_page"),
                        "snippet": s.get("snippet"),
                        "doc_code": alignment.get("doc_code", "IND-PV-REG-001"),
                        "doc_type": s.get("doc_type") or "regional_targets",
                    }
                    for s in snippets
                ]
                if not citations:
                    citations = [{
                        "title": "Regional Sales Targets FY2026",
                        "source_doc": "IND-PV-REG-001_Regional_Sales_Targets_FY2026.md",
                        "source_page": "",
                        "snippet": "FY2026 zone unit targets and H1/H2 phasing for plan vs actual reviews.",
                        "doc_code": "IND-PV-REG-001",
                        "doc_type": "regional_targets",
                    }]
                narr = generate_target_alignment_narration(alignment, citations)
                rdf = alignment["result_df"]
                scope = alignment.get("scope", "National")
                grain = alignment.get("grain", "monthly")
                return {
                    "result_df": rdf,
                    "sql": build_alignment_sql(scope, grain, alignment.get("fy_label", "FY2026")),
                    "evidence": {
                        "execution_path": "okf_target_alignment",
                        "resolution_source": "okf_reg_001",
                        "modified": False,
                        "alignment_scope": scope,
                        "alignment_grain": grain,
                        "alignment_status": narr.get("alignment_status"),
                    },
                    "narration": narr,
                    "result_summary": narr.get("result_summary"),
                    "force_narration": True,
                    "source_question": question,
                    "glossary_matches": [],
                    "okf_answer": True,
                }
    except Exception:
        pass

    snippets: list[dict] = []
    try:
        from features.okf_knowledge.okf_retriever import get_relevant_snippets
        snippets = get_relevant_snippets(question, top_k=4, max_context_chars=1400)
        # Keyword fallback if embedding miss
        if len(snippets) < 2 and is_ev_demand_question(question):
            snippets = get_relevant_snippets(
                "EV share electric powertrain demand reporting SOP-003",
                top_k=4,
                max_context_chars=1400,
            )
    except Exception:
        snippets = []

    share_df = None
    if is_ev_demand_question(question) and working_df is not None:
        share_df = compute_ev_share_by_year(working_df)

    if share_df is None and not snippets:
        return None

    citations = [
        {
            "title": s.get("title"),
            "source_doc": s.get("source_doc"),
            "source_page": s.get("source_page"),
            "snippet": s.get("snippet"),
            "doc_code": s.get("doc_code"),
            "doc_type": s.get("doc_type"),
        }
        for s in snippets
    ]

    if share_df is not None:
        headline, findings = _trend_summary(share_df)
        kb_bits = " ".join((s.get("snippet") or "")[:180] for s in snippets[:2])
        paras = [
            f"{headline} Per IND-PV-SOP-003, EV demand is tracked as unit share of "
            f"retail volume, not order count.",
            " ".join(findings),
        ]
        if kb_bits:
            paras.append(f"Business guidance: {kb_bits}")
        paras.append(
            "Drill EV share by make and region next; cite SOP-003 when presenting to leadership."
        )
        narrative = "\n\n".join(paras)
        narr = {
            "headline": headline,
            "narrative_text": narrative.strip(),
            "summary": headline,
            "key_findings": [],
            "recommendation": "",
            "knowledge_citations": citations,
            "result_summary": f"EV share by year — {len(share_df)} years",
        }
        return {
            "result_df": share_df,
            "sql": (
                "-- Deterministic EV share (IND-PV-SOP-003)\n"
                "SELECT YEAR(sales_date) AS year,\n"
                "  SUM(CASE WHEN engine_type = 'Electric' THEN order_qty ELSE 0 END) AS ev_units,\n"
                "  SUM(order_qty) AS total_units,\n"
                "  ROUND(100.0 * SUM(CASE WHEN engine_type = 'Electric' THEN order_qty ELSE 0 END)\n"
                "        / NULLIF(SUM(order_qty), 0), 2) AS ev_share_pct\n"
                "FROM fact_sales\nGROUP BY 1 ORDER BY 1"
            ),
            "evidence": {
                "execution_path": "okf_data",
                "resolution_source": "okf_sop_003",
                "modified": False,
            },
            "narration": narr,
            "result_summary": narr["result_summary"],
            "force_narration": True,
            "source_question": question,
            "glossary_matches": [],
            "okf_answer": True,
        }

    # Pure OKF / LLM grounded answer (handbooks, targets, strategy — no SQL)
    ctx_lines = []
    for s in snippets[:4]:
        dtype = s.get("doc_type") or "document"
        code = s.get("doc_code") or s.get("source_doc") or ""
        ctx_lines.append(
            f"- [{dtype}] {code} — {s.get('title')}: {s.get('snippet')}"
        )
    ctx = "\n".join(ctx_lines)
    prompt = f"""You are a business owner in India passenger-vehicle retail (OEM + dealer network).
Answer using ONLY the business documents below — NOT the semantic metric glossary.
Documents may be: handbook (dealer ops), regional_targets (FY goals), strategy_plan, or SOP.

Business document excerpts:
{ctx}

Question: {question}

Instructions:
- If the question asks for a target or threshold, quote the number from the document.
- Cite document IDs like IND-PV-REG-001 or IND-PV-HB-001.
- If data would also help, say what chart to run next — but answer the policy part first.
- 2-5 sentences, concrete, executive tone.

Answer:"""
    text = ""
    try:
        from core.llm_client import call_llm
        text = (call_llm(prompt) or "").strip()
    except Exception:
        text = ""
    if not text:
        # Fallback: stitch snippets as prose paragraphs (not bullets)
        bits = []
        for s in snippets[:3]:
            title = s.get("title") or "Guidance"
            snip = (s.get("snippet") or "").replace("\n", " ").strip()
            if len(snip) > 220:
                snip = snip[:217] + "…"
            bits.append(f"{title}: {snip}" if snip else str(title))
        text = "Based on our business SOPs:\n\n" + "\n\n".join(bits)
    narr = {
        "headline": "Business document answer",
        "narrative_text": text,
        "summary": text.split(".")[0][:160] if text else "See business knowledge docs.",
        "key_findings": [],
        "recommendation": (
            "Targets and strategy live in OKF documents — run a data query "
            "to compare actuals vs plan when needed."
        ),
        "knowledge_citations": citations,
        "result_summary": "Answered from OKF business documents",
    }
    return {
        "result_df": pd.DataFrame(
            [{
                "document": c.get("doc_code") or c.get("source_doc"),
                "type": c.get("doc_type") or "document",
                "section": c.get("title"),
                "excerpt": (c.get("snippet") or "")[:240],
            } for c in citations]
        ) if citations else pd.DataFrame(),
        "sql": "-- Answered from OKF business documents (not business_glossary.yaml)",
        "evidence": {
            "execution_path": "okf",
            "resolution_source": "okf_knowledge",
            "modified": False,
        },
        "narration": narr,
        "result_summary": narr["result_summary"],
        "force_narration": True,
        "source_question": question,
        "glossary_matches": [],
        "okf_answer": True,
    }
