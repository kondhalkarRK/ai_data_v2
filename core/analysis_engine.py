"""
core/analysis_engine.py
"""
import re
import pandas as pd

from core.llm_client import call_llm

# ─────────────────────────────────────────────────────────────────
# COMBINED ANALYSIS ENGINE — Summary + Insights + Recommendation
# Single LLM call replaces two separate calls
# ─────────────────────────────────────────────────────────────────
def generate_analysis(
    result: pd.DataFrame,
    question: str,
    extra_context: str = "",          # ← NEW: semantic_context passed from tab_query
) -> dict:
    """
    Single LLM call that returns summary, facts and recommendation.
    Returns dict with keys: 'summary', 'facts', 'recommendation'
    Falls back gracefully if parsing fails.

    Parameters
    ----------
    result        : Query result DataFrame to analyse.
    question      : The original natural-language question the user asked.
    extra_context : Optional semantic context string (business glossary +
                    column definitions) injected into the LLM prompt so the
                    model uses correct domain terminology in its output.
    """
    num_cols = result.select_dtypes(include="number").columns.tolist()
    str_cols = result.select_dtypes(exclude="number").columns.tolist()

    # ── Smart sample — send ALL cols for small results ──────────────────────
    if len(result) <= 15 and len(result.columns) <= 12:
        sample_df = result.head(10)
    else:
        keep_cols = str_cols[:1] + num_cols[:3]
        sample_df = result[keep_cols].head(8) if keep_cols else result.head(8)
    sample_str = sample_df.to_csv(index=False)

    # ── Compact stats — top 3 numeric cols only ──────────────────────────────
    stats_lines = []
    for c in num_cols[:3]:
        col_s = pd.to_numeric(result[c], errors="coerce").dropna()
        if len(col_s):
            stats_lines.append(
                f"{c}: total={round(float(col_s.sum()),2)}, "
                f"avg={round(float(col_s.mean()),2)}, "
                f"max={round(float(col_s.max()),2)}, "
                f"min={round(float(col_s.min()),2)}"
            )

    # ── Compact pre-analysis ─────────────────────────────────────────────────
    context_lines = []
    if num_cols and str_cols:
        col   = pd.to_numeric(result[num_cols[0]], errors="coerce").fillna(0)
        total = col.sum()
        if total > 0:
            top1_pct = round(col.nlargest(1).sum() / total * 100, 1)
            top3_pct = round(col.nlargest(3).sum() / total * 100, 1)
            context_lines.append(
                f"Concentration: top-1={top1_pct}%, top-3={top3_pct}% of {num_cols[0]}"
            )
    if num_cols:
        col = pd.to_numeric(result[num_cols[0]], errors="coerce").dropna()
        if len(col) >= 4:
            half      = len(col) // 2
            h1_avg    = round(float(col.iloc[:half].mean()), 2)
            h2_avg    = round(float(col.iloc[half:].mean()), 2)
            chg       = round((h2_avg - h1_avg) / h1_avg * 100, 1) if h1_avg else 0
            direction = (
                "accelerating" if chg > 5
                else ("decelerating" if chg < -5 else "stable")
            )
            context_lines.append(
                f"Trend: {direction} ({chg:+.1f}%), H1={h1_avg}, H2={h2_avg}"
            )

    # ── [SEMANTIC] Build optional semantic block for the prompt ─────────────
    # Kept deliberately short so it does not push the prompt over token limits.
    # Only included when extra_context is a non-empty string.
    semantic_block = ""
    if extra_context and extra_context.strip():
        # Truncate to 400 chars to stay within token budget
        trimmed = extra_context.strip()[:400]
        semantic_block = (
            f"BUSINESS GLOSSARY / SEMANTIC CONTEXT:\n"
            f"{trimmed}\n"
            f"(Use the definitions above to ensure correct terminology in your response.)\n\n"
        )
    # ────────────────────────────────────────────────────────────────────────

    # ── Single compact prompt ────────────────────────────────────────────────
    prompt = (
        f'QUESTION: "{question}"\n'
        f"TOTAL ROWS: {len(result)} | COLUMNS: {list(result.columns)}\n\n"
        # ── [SEMANTIC #1] Glossary injected right after question context ──────
        f"{semantic_block}"
        # ─────────────────────────────────────────────────────────────────────
        f"DATA (CSV):\n{sample_str}\n"
        f"STATS: {'; '.join(stats_lines) or 'N/A'}\n"
        f"CONTEXT: {' | '.join(context_lines) or 'N/A'}\n\n"
        f"You are a senior business analyst. Analyse the data above and respond in EXACTLY this format:\n\n"
        f"SUMMARY: [2-3 sentences directly answering the question with exact numbers from data]\n\n"
        f"FACTS:\n"
        f"• [Fact 1 with specific number]\n"
        f"• [Fact 2 with specific number]\n"
        f"• [Fact 3 with specific number]\n\n"
        f"RECOMMENDATION: [1-2 sentences of specific actionable advice based on data]\n\n"
        f"RULES:\n"
        f"- Use ONLY numbers from the data provided\n"
        f"- SUMMARY must directly answer the question asked\n"
        f"- Each FACT must cite a real number\n"
        f"- No vague words like 'significant' or 'many'\n"
        f"- No repetition between sections\n"
        f"- Total response must be under 180 words"
    )

    raw = call_llm(prompt)
    if not raw:
        return {
            "summary":        "Could not generate summary.",
            "facts":          [],
            "recommendation": "",
        }

    return _parse_analysis_response(raw)


# ─────────────────────────────────────────────────────────────────
# PARSER — unchanged
# ─────────────────────────────────────────────────────────────────
def _parse_analysis_response(raw: str) -> dict:
    """
    Parses the structured LLM response into summary, facts, recommendation.
    Robust fallback if format is not followed perfectly.
    """
    result = {"summary": "", "facts": [], "recommendation": ""}

    try:
        # Extract SUMMARY
        summary_match = re.search(
            r'SUMMARY:\s*(.+?)(?=FACTS:|RECOMMENDATION:|$)',
            raw, re.DOTALL | re.IGNORECASE,
        )
        if summary_match:
            result["summary"] = summary_match.group(1).strip()

        # Extract FACTS — bullet points
        facts_match = re.search(
            r'FACTS:\s*(.+?)(?=RECOMMENDATION:|$)',
            raw, re.DOTALL | re.IGNORECASE,
        )
        if facts_match:
            facts_block = facts_match.group(1).strip()
            bullets     = re.findall(r'[•\-\*]\s*(.+)', facts_block)
            if bullets:
                result["facts"] = [b.strip() for b in bullets[:3]]
            else:
                lines = [l.strip() for l in facts_block.split("\n") if l.strip()]
                result["facts"] = lines[:3]

        # Extract RECOMMENDATION
        rec_match = re.search(
            r'RECOMMENDATION:\s*(.+?)$',
            raw, re.DOTALL | re.IGNORECASE,
        )
        if rec_match:
            result["recommendation"] = rec_match.group(1).strip()

        # Fallback — if parsing totally failed, put everything in summary
        if not result["summary"] and not result["facts"]:
            result["summary"] = raw.strip()

    except Exception:
        result["summary"] = raw.strip()

    return result