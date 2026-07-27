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
        Builds the static semantic context block.
        Used as the core business model description for GPT.
        """
        loader = self._loader

        # ── Business Model Header ────────────────────────────────
        lines = [
            "═══════════════════════════════════════════════",
            "BUSINESS MODEL — SEMANTIC LAYER",
            "═══════════════════════════════════════════════",
            "",
        ]

        # ── Fact Table ───────────────────────────────────────────
        tables = loader.get_tables()
        fact_tables = [
            (k, v) for k, v in tables.items()
            if v.get("type") == "fact"
        ]
        if fact_tables:
            lines.append("FACT TABLE:")
            for tname, tval in fact_tables:
                lines.append(
                    f"  {tname} — {tval.get('display_name', tname)}"
                )
                lines.append(
                    f"  Grain: {tval.get('grain', 'N/A')}"
                )
            lines.append("")

        # ── Dimension Tables ─────────────────────────────────────
        dim_tables = [
            (k, v) for k, v in tables.items()
            if v.get("type") == "dimension"
        ]
        if dim_tables:
            lines.append("DIMENSION TABLES:")
            for tname, tval in dim_tables:
                lines.append(
                    f"  {tname} — {tval.get('display_name', tname)}"
                )
            lines.append("")

        # ── Semantic Dimensions ──────────────────────────────────
        dimensions = loader.get_dimensions()
        if dimensions:
            lines.append("BUSINESS DIMENSIONS:")
            for dname, dval in dimensions.items():
                display  = dval.get("display_name", dname)
                src_tbl  = dval.get("source_table", "")
                attrs    = dval.get("attributes", [])
                syns     = dval.get("synonyms", [])[:4]
                syn_str  = ", ".join(syns) if syns else ""
                lines.append(
                    f"  {display}"
                    f"  (source: {src_tbl})"
                    + (f"  [also: {syn_str}]" if syn_str else "")
                )
                if attrs:
                    lines.append(f"    Attributes: {', '.join(attrs)}")
            lines.append("")

        # ── Semantic Measures ────────────────────────────────────
        measures = loader.get_measures()
        if measures:
            lines.append("BUSINESS MEASURES:")
            for mname, mval in measures.items():
                display = mval.get("display_name", mname)
                expr    = mval.get("expression", "")
                fmt     = mval.get("format", "")
                syns    = mval.get("synonyms", [])[:4]
                syn_str = ", ".join(syns) if syns else ""
                lines.append(
                    f"  {display}: {expr}"
                    + (f"  [format: {fmt}]" if fmt else "")
                    + (f"  [also: {syn_str}]" if syn_str else "")
                )
            lines.append("")

        # ── Relationships ────────────────────────────────────────
        rel_strings = loader.get_relationship_strings()
        if rel_strings:
            lines.append("RELATIONSHIPS:")
            for rel in rel_strings:
                lines.append(f"  {rel}")
            lines.append("")

        # ── Available Attributes ─────────────────────────────────
        attrs = loader.get_available_attributes()
        if attrs:
            lines.append("AVAILABLE ATTRIBUTES:")
            lines.append(f"  {', '.join(attrs)}")
            lines.append("")

        lines.append("═══════════════════════════════════════════════")

        return "\n".join(lines)

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
            # Attach SQL expressions
            loader    = self._loader
            measures  = loader.get_measures()
            expr_map  = loader.get_measure_expressions()

            lines.append("MEASURES TO USE:")
            for m in resolved_measures:
                expr = expr_map.get(m, "")
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

    def build_conversation_context(self, conv_state: dict | None) -> str:
        """Inject prior turn info for follow-up awareness."""
        if not conv_state:
            return ""
        lines = ["CONVERSATION CONTEXT:"]
        metric = conv_state.get("prior_metric")
        dims = conv_state.get("prior_dimensions") or []
        filters = conv_state.get("prior_filters") or {}
        if metric:
            lines.append(f"  Prior metric: {metric}")
        if dims:
            lines.append(f"  Prior dimensions: {', '.join(map(str, dims))}")
        if filters:
            filt = ", ".join(f"{k}={v}" for k, v in filters.items())
            lines.append(f"  Prior filters: {filt}")
        if conv_state.get("is_followup"):
            lines.append("  This appears to be a follow-up query.")
        if len(lines) == 1:
            return ""
        return "\n".join(lines)

    def build_scope_context(self) -> str:
        """Tell LLM what is in/out of scope."""
        return (
            "SCOPE: Answer questions about automotive sales data only.\n"
            "Cannot: write code, modify data, make future predictions."
        )

    def build_full_context(
        self,
        question: str,
        df:       pd.DataFrame,
        conv_state: dict | None = None,
    ) -> str:
        """
        Builds the complete semantic context for a user question.

        This is the main entry point called from nlq_to_sql().

        Combines:
        1. Base semantic model context
        2. Vector search entity resolutions
        3. Physical column mapping
        4. Metric / conversation / scope blocks (ISANA)

        Args:
            question: User's natural language question
            df:       Working DataFrame
            conv_state: Optional conversation state dict

        Returns:
            Complete context string for GPT prompt
        """
        # ── Step 1: Resolve semantic entities ───────────────────
        resolutions = self._search.resolve_query_terms(question)

        # ── Step 2: Build context blocks ─────────────────────────
        base_ctx     = self.build_base_context()
        resolved_ctx = self.build_resolved_context(question, resolutions)
        column_ctx   = self.build_physical_column_map(df)
        metric_ctx   = self.build_metric_context()
        scope_ctx    = self.build_scope_context()
        conv_ctx     = self.build_conversation_context(conv_state)

        # ── Step 3: Combine ──────────────────────────────────────
        blocks = [
            base_ctx,
            metric_ctx,
            scope_ctx,
            resolved_ctx,
            column_ctx,
        ]
        if conv_ctx:
            blocks.insert(3, conv_ctx)

        full_context = "\n\n".join(blocks)

        return full_context

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