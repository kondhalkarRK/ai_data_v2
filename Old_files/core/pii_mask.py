"""
core/pii_mask.py
Mask personally identifiable information for display only (not query engine).
"""
from __future__ import annotations

import re

import pandas as pd

_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$",
)
_PHONE_RE = re.compile(
    r"^\+?[\d\s().-]{7,18}$",
)

_PII_COL_PATTERNS = (
    "email", "e_mail", "mail_id",
    "phone", "mobile", "cell", "telephone", "contact_number",
    "ssn", "social_security", "pan", "aadhar", "aadhaar",
    "passport", "credit_card", "card_number",
    "first_name", "lastname", "last_name", "firstname",
    "full_name", "salesperson_name", "customer_name",
    "corp_id", "employee_id", "national_id",
)


def _is_pii_column(name: str) -> bool:
    n = str(name).lower().replace("-", "_").replace(" ", "_")
    return any(p in n for p in _PII_COL_PATTERNS)


def _mask_email(val: str) -> str:
    s = str(val).strip()
    if "@" not in s:
        return s
    local, _, domain = s.partition("@")
    if not local:
        return f"***@{domain}"
    show = local[0] if len(local) == 1 else local[:2]
    return f"{show}***@{domain}"


def _mask_phone(val: str) -> str:
    digits = re.sub(r"\D", "", str(val))
    if len(digits) < 4:
        return "***"
    return f"***-***-{digits[-4:]}"


def _mask_name(val: str) -> str:
    s = str(val).strip()
    if not s:
        return s
    parts = s.split()
    masked = []
    for p in parts:
        if len(p) <= 1:
            masked.append("*")
        else:
            masked.append(p[0] + "***")
    return " ".join(masked)


def _mask_cell(val, col_name: str) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return val
    s = str(val).strip()
    if not s:
        return s
    low_col = str(col_name).lower()
    if "email" in low_col or _EMAIL_RE.match(s):
        return _mask_email(s)
    if any(x in low_col for x in ("phone", "mobile", "tel", "cell")) or (
        _PHONE_RE.match(s) and sum(c.isdigit() for c in s) >= 7
    ):
        return _mask_phone(s)
    if any(x in low_col for x in ("name", "first", "last", "salesperson", "customer")):
        return _mask_name(s)
    if any(x in low_col for x in ("corp_id", "employee", "ssn", "pan", "aadhar", "passport")):
        return "***" if len(s) > 3 else "***"
    return s


def mask_pii_for_display(df: pd.DataFrame | None) -> pd.DataFrame:
    """Return a copy with PII columns / values masked for UI display."""
    if df is None or df.empty:
        return df

    out = df.copy()
    pii_cols = [c for c in out.columns if _is_pii_column(c)]

    # Also scan object columns for email-like values
    for c in out.columns:
        if c in pii_cols:
            continue
        if out[c].dtype == object:
            sample = out[c].dropna().astype(str).head(20)
            if len(sample) and sample.str.match(_EMAIL_RE).mean() > 0.5:
                pii_cols.append(c)

    for c in pii_cols:
        try:
            out[c] = out[c].apply(lambda v, col=c: _mask_cell(v, col))
        except Exception:
            pass
    return out


def pii_columns_found(df: pd.DataFrame | None) -> list[str]:
    if df is None or df.empty:
        return []
    found = [str(c) for c in df.columns if _is_pii_column(c)]
    return found
