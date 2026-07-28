# semantic/semantic_context_builder.py
# Builds semantic metadata context for GPT — replaces raw schema.
# Capgemini AI Data Platform V10

from __future__ import annotations

import pandas as pd
from typing import Optional

from semantic.semantic_loader import get_semantic_loader
from semantic.semantic_vector_search import get_vector_search


# ════════════════════════════════════════════════════════════════
# SEMANTIC CONTEXT BUILDER
# ════════════════════════════════════════════════════════════════

class SemanticContextBuilder:
    """
    Builds a rich semantic context string for GPT prompt injection.

    Replaces raw column schema with:
    - Business model overview
    - Semantic measures with SQL expressions
    - Semantic dimensions with attributes
    - Table relationships
    - Resolved entities from user question
    - Physical column mapping for SQL generation

    This ensures GPT generates SQL using correct
    physical column names while understanding
    the business meaning of each concept.
    """

    def __init__(self):
        self._loader = get_semantic_loader()
        self._search = get_vector_search()

    def build_base_context(self) -> str:
        """
        Builds the static semantic context block including enhanced glossary.
        """
        loader = self._loader
        lines = [
            "═══════════════════════════════════════════════",
            "BUSINESS MODEL — SEMANTIC LAYER",
            "═══════════════════════════════════════════════",
            "",
        ]

        # Glossary measures / terms with SQL
        glossary = loader.get_glossary()
        if glossary:
            lines.append("BUSINESS GLOSSARY (canonical terms):")
            for term, val in glossary.items():
                display = val.get("display_label") or term
                expr = val.get("sql_expression") or val.get("display_expression") or ""
                if isinstance(expr, str):
                    expr = " ".join(expr.split())
                fmt = val.get("format", "")
                syns = val.get("synonyms", [])[:6]
                syn_str = ", ".join(syns) if syns else ""
                lines.append(
                    f"  {display}"
                    + (f": {expr}" if expr else "")
                    + (f"  [{fmt}]" if fmt else "")
                    + (f"  [also: {syn_str}]" if syn_str else "")
                )
                for rule in (val.get("calculation_rules") or [])[:3]:
                    lines.append(f"    rule: {rule}")
                for ex in (val.get("example_questions") or [])[:2]:
                    lines.append(f"    e.g. {ex}")
            lines.append("")

        # SQL patterns
        patterns = loader.get_sql_patterns()
        if patterns:
            lines.append("SQL PATTERNS:")
            for pname, pval in patterns.items():
                desc = pval.get("description", pname)
                triggers = pval.get("trigger_words", [])
                if isinstance(triggers, list):
                    trig = ", ".join(str(t) for t in triggers[:8])
                else:
                    trig = str(triggers)
                lines.append(f"  {pname}: {desc}")
                if trig:
                    lines.append(f"    triggers: {trig}")
                if pval.get("pattern"):
                    pat = " ".join(str(pval["pattern"]).split())
                    lines.append(f"    pattern: {pat}")
            lines.append("")

        # Domain rules
        rules = loader.get_domain_rules()
        if rules:
            lines.append("DOMAIN RULES:")
            for section in ("always_rules", "never_rules", "default_behaviours"):
                for r in rules.get(section, []) or []:
                    lines.append(f"  - [{section}] {r}")
            lines.append("")

        # Semantic model measures (fallback/extra)
        measures = loader.get_measures()
        if measures:
            lines.append("SEMANTIC MODEL MEASURES:")
            for mname, mval in measures.items():
                display = mval.get("display_name", mname)
                expr = mval.get("expression", "")
                lines.append(f"  {display}: {expr}")
            lines.append("")

        dimensions = loader.get_dimensions()
        if dimensions:
            lines.append("BUSINESS DIMENSIONS:")
            for dname, dval in dimensions.items():
                display = dval.get("display_name", dname)
                syns = dval.get("synonyms", [])[:4]
                syn_str = ", ".join(syns) if syns else ""
                lines.append(
                    f"  {display}"
                    + (f"  [also: {syn_str}]" if syn_str else "")
                )
            lines.append("")

        lines.append("═══════════════════════════════════════════════")
        return "\n".join(lines)

    def build_glossary_sql_hints(self, question: str) -> str:
        """Scan question for glossary term matches and return SQL hint block for LLM."""
        try:
            if not question:
                return ""
            matches = self._loader.get_glossary_hints_for_question(question)
            if not matches:
                return ""

            lines = [
                "───────────────────────────────────────────",
                "SQL HINTS FROM BUSINESS GLOSSARY:",
                "───────────────────────────────────────────",
            ]
            for m in matches:
                token = m.get("matched_token", "")
                term = m.get("term_name", "")
                expr = m.get("sql_expression")
                if expr:
                    lines.append(f"  '{token}' → use: {expr}")
                src = m.get("source_column")
                is_agg = isinstance(expr, str) and (
                    "SUM(" in expr.upper() or "COUNT(" in expr.upper() or "/" in expr
                )
                if src and (not expr or (isinstance(expr, str) and expr.startswith("column "))):
                    if not is_agg:
                        lines.append(f"  '{token}' → physical column: {src}")

                grains = m.get("time_grains") or {}
                if grains:
                    for gname, gexpr in grains.items():
                        gexpr_c = " ".join(str(gexpr).split())
                        lines.append(f"  '{gname}' → use: {gexpr_c}")

                rules = m.get("calculation_rules") or []
                if rules:
                    lines.append(f"  Rules for {term}:")
                    for rule in rules[:3]:
                        lines.append(f"    • {rule}")

                disamb = m.get("disambiguation") or []
                if disamb:
                    lines.append(f"  Note: {disamb[0]}")

            lines.append("───────────────────────────────────────────")
            return "\n".join(lines)
        except Exception:
            return ""

    def build_domain_rules_block(self) -> str:
        """Return formatted domain rules from glossary for LLM instruction."""
        try:
            rules = self._loader.get_domain_rules() or {}
            if not rules:
                return ""

            lines = [
                "───────────────────────────────────────────",
                "DOMAIN RULES (always follow these exactly):",
                "───────────────────────────────────────────",
            ]
            always = rules.get("always_rules") or []
            if always:
                lines.append("ALWAYS:")
                for r in always:
                    lines.append(f"  ✓ {r}")
            never = rules.get("never_rules") or []
            if never:
                lines.append("NEVER:")
                for r in never:
                    lines.append(f"  ✗ {r}")
            defaults = rules.get("default_behaviours") or []
            if defaults:
                lines.append("DEFAULTS:")
                for r in defaults:
                    lines.append(f"  → {r}")
            lines.append("───────────────────────────────────────────")
            return "\n".join(lines)
        except Exception:
            return ""

    def build_conversation_context(
        self,
        conv_state: dict | None = None,
        chat_history: str | None = None,
    ) -> str:
        """Inject prior conversation context for follow-up query awareness."""
        try:
            has_hist = bool(chat_history and str(chat_history).strip())
            has_conv = bool(conv_state) and (
                conv_state.get("prior_metric")
                or conv_state.get("prior_dimensions")
                or conv_state.get("is_followup")
            )
            if not has_hist and not has_conv:
                return ""

            lines = [
                "───────────────────────────────────────────",
                "CONVERSATION CONTEXT:",
                "───────────────────────────────────────────",
            ]
            if has_hist:
                lines.append(f"Recent conversation:\n{chat_history}")
            if conv_state:
                if conv_state.get("prior_metric"):
                    lines.append(f"Prior metric used: {conv_state['prior_metric']}")
                dims = conv_state.get("prior_dimensions") or []
                if dims:
                    lines.append(f"Prior dimensions: {', '.join(map(str, dims))}")
                if conv_state.get("is_followup"):
                    lines.append(
                        "Note: This appears to be a follow-up query.\n"
                        "     Consider inheriting prior context unless\n"
                        "     user explicitly changes topic."
                    )
            lines.append("───────────────────────────────────────────")
            return "\n".join(lines)
        except Exception:
            return ""

    def build_resolved_glossary_block(self, question: str, resolutions: dict) -> str:
        """Pull full glossary definitions for terms relevant to this question."""
        loader = self._loader
        glossary = loader.get_glossary()
        relevant: list[str] = []

        # From vector resolutions
        for m in resolutions.get("resolved_measures", []) or []:
            relevant.append(str(m))
        for d in resolutions.get("resolved_dimensions", []) or []:
            relevant.append(str(d))
        for orig, canon in (resolutions.get("resolution_map") or {}).items():
            relevant.append(str(canon))

        # From synonym scan
        q = (question or "").lower()
        for term, val in glossary.items():
            if term.lower() in q:
                relevant.append(term)
            for syn in val.get("synonyms", []) or []:
                if str(syn).lower() in q:
                    relevant.append(term)

        # de-dupe
        seen = set()
        terms = []
        for t in relevant:
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            # resolve to glossary key
            hit = None
            for gterm in glossary:
                if gterm.lower() == key or gterm.lower() == t.lower():
                    hit = gterm
                    break
            if hit is None:
                for gterm, gval in glossary.items():
                    if any(str(s).lower() == key for s in (gval.get("synonyms") or [])):
                        hit = gterm
                        break
                    if (gval.get("display_label") or "").lower() == key:
                        hit = gterm
                        break
            if hit and hit not in terms:
                terms.append(hit)

        if not terms:
            return ""

        lines = [
            "───────────────────────────────────────────────",
            "RESOLVED TERMS (from business glossary):",
            "───────────────────────────────────────────────",
        ]
        for term in terms[:8]:
            val = glossary.get(term, {})
            lines.append(f"TERM: {term}")
            if val.get("definition"):
                defn = " ".join(str(val["definition"]).split())
                lines.append(f"  definition: {defn[:220]}")
            expr = val.get("sql_expression") or val.get("display_expression")
            if expr:
                lines.append(f"  sql: {' '.join(str(expr).split())}")
            for rule in (val.get("calculation_rules") or [])[:3]:
                lines.append(f"  rule: {rule}")
            for d in (val.get("disambiguation") or [])[:2]:
                lines.append(f"  disambiguation: {d}")
            lines.append("")
        return "\n".join(lines)

    def build_full_context(
        self,
        question: str,
        df:       pd.DataFrame,
        conv_state: dict | None = None,
        chat_history: str | None = None,
    ) -> str:
        """
        Complete semantic context for LLM SQL generation.
        Combines base model, resolved entities, columns, glossary hints,
        domain rules, and conversation context.
        """
        try:
            resolutions = self._search.resolve_query_terms(question)
        except Exception:
            resolutions = {
                "resolved_measures": [],
                "resolved_dimensions": [],
                "resolved_attributes": [],
                "resolution_map": {},
            }

        base_ctx = self.build_base_context()
        try:
            resolved_ctx = self.build_resolved_context(question, resolutions)
        except Exception:
            resolved_ctx = ""
        try:
            column_ctx = self.build_physical_column_map(df)
        except Exception:
            column_ctx = ""

        glossary_hints = self.build_glossary_sql_hints(question)
        domain_rules = self.build_domain_rules_block()
        conv_ctx = self.build_conversation_context(conv_state, chat_history)

        blocks = [b for b in [
            base_ctx,
            resolved_ctx,
            column_ctx,
            glossary_hints,
            domain_rules,
            conv_ctx,
        ] if b and str(b).strip()]

        return "\n\n".join(blocks)

    def build_resolved_context(
        self,
        question:    str,
        resolutions: dict,
    ) -> str:
        """
        Builds the resolved entity context block based on
        what the vector search resolved from the user question.

        Args:
            question:    Original user question
            resolutions: Output from SemanticVectorSearch.resolve_query_terms()

        Returns:
            Formatted string block for GPT prompt injection
        """
        lines = [
            "───────────────────────────────────────────────",
            "RESOLVED SEMANTIC ENTITIES FOR THIS QUESTION:",
            "───────────────────────────────────────────────",
        ]

        resolved_measures   = resolutions.get("resolved_measures", [])
        resolved_dimensions = resolutions.get("resolved_dimensions", [])
        resolved_attributes = resolutions.get("resolved_attributes", [])
        resolution_map      = resolutions.get("resolution_map", {})

        if resolved_measures:
            # Prefer glossary SQL expressions, then semantic model measures
            loader = self._loader
            expr_map = dict(loader.get_measure_expressions() or {})
            try:
                expr_map.update(loader.get_all_sql_expressions() or {})
            except Exception:
                pass

            lines.append("MEASURES TO USE:")
            for m in resolved_measures:
                expr = expr_map.get(m, "")
                if not expr:
                    try:
                        expr = loader.get_term_sql_expression(m) or ""
                    except Exception:
                        expr = ""
                lines.append(
                    f"  {m}: {expr}" if expr else f"  {m}"
                )

        if resolved_dimensions:
            lines.append("DIMENSIONS TO USE:")
            for d in resolved_dimensions:
                lines.append(f"  {d}")

        if resolved_attributes:
            lines.append("ATTRIBUTES TO USE:")
            for a in resolved_attributes:
                lines.append(f"  {a}")

        if resolution_map:
            lines.append("TERM RESOLUTIONS (user word → business concept):")
            for orig, canon in resolution_map.items():
                if orig.lower() != canon.lower():
                    lines.append(f"  '{orig}' → '{canon}'")

        lines.append("───────────────────────────────────────────────")

        return "\n".join(lines)

    def build_physical_column_map(
        self,
        df: pd.DataFrame,
    ) -> str:
        """
        Builds a physical column reference block.
        Maps semantic concepts to actual DataFrame columns.

        This ensures GPT always uses correct physical column
        names in the generated SQL.

        Args:
            df: The working DataFrame (joined dataset)

        Returns:
            Formatted string for GPT prompt injection
        """
        actual_cols = list(df.columns)
        loader      = self._loader
        tables      = loader.get_tables()

        lines = [
            "───────────────────────────────────────────────",
            "PHYSICAL COLUMN REFERENCE (use these in SQL):",
            "───────────────────────────────────────────────",
        ]

        # Map display names to physical columns present in df
        matched: list[str] = []
        for table_key, table_val in tables.items():
            for col_key, col_val in table_val.get("columns", {}).items():
                display = col_val.get("display_name", col_key)
                role    = col_val.get("role", "")
                # Check if physical column exists in df
                if col_key in actual_cols:
                    matched.append(
                        f"  {display} → {col_key}"
                        + (f"  [{role}]" if role else "")
                    )

        if matched:
            lines.extend(matched)
        else:
            # Fallback — list all df columns
            lines.append(
                f"  Available columns: {', '.join(actual_cols)}"
            )

        lines.append("───────────────────────────────────────────────")

        return "\n".join(lines)

    def build_metric_context(self) -> str:
        """Show LLM all known business metrics from metric registry."""
        lines = [
            "KNOWN BUSINESS METRICS:",
        ]
        try:
            exprs = self._loader.get_metric_expressions()
            labels = self._loader.get_metric_display_labels()
            reg = self._loader.get_metric_registry() or {}
            formats: dict[str, str] = {}
            for bucket in ("measures", "derived_measures", "metrics"):
                for key, val in (reg.get(bucket) or {}).items():
                    formats[key] = val.get("format", "")
            if not exprs:
                # Fallback to semantic model measures
                for name, expr in self._loader.get_measure_expressions().items():
                    lines.append(f"  {name}: {expr}")
            else:
                for key, expr in exprs.items():
                    label = labels.get(key, key)
                    fmt = formats.get(key, "")
                    fmt_bit = f" [{fmt}]" if fmt else ""
                    lines.append(f"  {label}: {expr}{fmt_bit}")
        except Exception:
            lines.append("  Revenue: SUM(total_sales) [currency]")
            lines.append("  Units Sold: SUM(order_qty) [integer]")
        return "\n".join(lines)

    def build_scope_context(self) -> str:
        """Tell LLM what is in/out of scope."""
        return (
            "SCOPE: Answer questions about automotive sales data only.\n"
            "Cannot: write code, modify data, make future predictions."
        )

    def get_resolutions(self, question: str) -> dict:
        """
        Returns just the resolution dict for a question.
        Used for logging/debugging in the UI.
        """
        return self._search.resolve_query_terms(question)


# ── Module-level singleton ───────────────────────────────────────
_context_builder_instance: SemanticContextBuilder | None = None


def get_context_builder() -> SemanticContextBuilder:
    """
    Returns singleton SemanticContextBuilder instance.
    """
    global _context_builder_instance
    if _context_builder_instance is None:
        _context_builder_instance = SemanticContextBuilder()
    return _context_builder_instance