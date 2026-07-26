"""
core/utils.py
"""
import io
import re
import pandas as pd
import streamlit as st

# ─────────────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────────────
def clean_name(n): return n.replace(".csv", "").lower().strip()
def norm(t):       return re.sub(r'[^a-z0-9]', '', str(t).lower())


def _get_session_dfs():
    dfs = getattr(st.session_state, "dfs", None)
    if dfs is None:
        dfs = {}
        setattr(st.session_state, "dfs", dfs)
    return dfs


def load_files(files):
    dfs = _get_session_dfs()

    for f in files:
        if f is None:
            continue

        name = getattr(f, "name", "uploaded_file")
        if not name.lower().endswith(".csv"):
            raise ValueError(f"Unsupported file type for {name}. Please upload a CSV file.")

        try:
            f.seek(0)
        except Exception:
            pass

        try:
            raw = f.read()
        except Exception as e:
            raise ValueError(f"Could not read uploaded file {name}: {e}") from e

        if raw is None:
            raise ValueError(f"Uploaded file {name} is empty.")

        if isinstance(raw, bytes):
            if not raw.strip():
                raise ValueError(f"Uploaded file {name} is empty.")
            text = raw.decode("utf-8-sig")
        else:
            text = str(raw)

        if not text.strip():
            raise ValueError(f"Uploaded file {name} is empty.")

        try:
            df = pd.read_csv(io.StringIO(text))
        except Exception as e:
            raise ValueError(f"Unable to parse CSV file {name}: {e}") from e

        for col in df.columns:
            if "date" in col.lower():
                df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)

        dfs[clean_name(name)] = df
