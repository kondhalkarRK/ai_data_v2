# semantic/industry_packs.py
#
# INDUSTRY PACK SWITCHER — additive module, does not modify any
# existing file or function.
#
# Each "pack" is a folder under semantic/packs/<pack_id>/ containing:
#   - semantic_model.yaml
#   - business_glossary.yaml
#   - pack.yaml   (label / icon / description, for display only)
#
# Activating a pack copies that pack's two YAML files on top of the
# live paths semantic_loader.py already reads from
# (semantic/semantic_model.yaml, semantic/business_glossary.yaml),
# then resets the existing module-level singleton caches in
# semantic_loader.py / semantic_vector_search.py /
# semantic_context_builder.py so they reload the new content on the
# next access. Those three files are not edited — this module simply
# reaches into their existing public singleton getters and resets the
# module-level cache variable via the module object itself.
#
# NOTE (read before using in a shared/production deployment):
# the singleton caches this resets are plain Python module globals,
# i.e. process-wide, not per Streamlit session. That's exactly right
# for a single-user demo/showcase environment, but if this app is ever
# deployed for concurrent multi-user access, switching a pack in one
# browser session would change the active semantic model for every
# other concurrent session too. Fine for the isolated demo this was
# built for; would need session-scoped semantic objects (a separate,
# larger change) before going to shared production.

from __future__ import annotations

import os
import shutil
import yaml

import streamlit as st

_DIR       = os.path.dirname(os.path.abspath(__file__))
_PACKS_DIR = os.path.join(_DIR, "packs")

_LIVE_MODEL_PATH    = os.path.join(_DIR, "semantic_model.yaml")
_LIVE_GLOSSARY_PATH = os.path.join(_DIR, "business_glossary.yaml")

_DEFAULT_PACK_ID = "automotive"


def list_packs() -> list[dict]:
    """
    Scan semantic/packs/ for valid packs (folders containing both
    semantic_model.yaml and business_glossary.yaml).

    Returns a list of dicts: {id, label, icon, description}
    sorted alphabetically by label.
    """
    packs: list[dict] = []

    if not os.path.isdir(_PACKS_DIR):
        return packs

    for entry in sorted(os.listdir(_PACKS_DIR)):
        pack_dir = os.path.join(_PACKS_DIR, entry)
        model_path    = os.path.join(pack_dir, "semantic_model.yaml")
        glossary_path = os.path.join(pack_dir, "business_glossary.yaml")

        if not (os.path.isfile(model_path) and os.path.isfile(glossary_path)):
            continue

        label = entry.replace("_", " ").title()
        icon  = "📦"
        description = ""

        meta_path = os.path.join(pack_dir, "pack.yaml")
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = yaml.safe_load(f) or {}
                label       = meta.get("label", label)
                icon        = meta.get("icon", icon)
                description = meta.get("description", "")
            except Exception:
                pass

        packs.append({
            "id": entry,
            "label": label,
            "icon": icon,
            "description": description,
        })

    packs.sort(key=lambda p: p["label"])
    return packs


def get_active_pack_id() -> str:
    """Return the currently active pack id (default: automotive)."""
    return st.session_state.get("industry_pack_id", _DEFAULT_PACK_ID)


def _reset_semantic_singletons() -> None:
    """
    Reset the existing module-level singleton caches so the next call
    to get_semantic_loader() / get_vector_search() / get_context_builder()
    reloads fresh from the (now-overwritten) live YAML files.

    This does not edit semantic_loader.py, semantic_vector_search.py or
    semantic_context_builder.py — it only resets the module-global
    variable those files already define and use internally.
    """
    import semantic.semantic_loader as _sl
    import semantic.semantic_vector_search as _svs
    import semantic.semantic_context_builder as _scb

    _sl._loader_instance          = None
    _svs._search_instance         = None
    _scb._context_builder_instance = None


def activate_pack(pack_id: str) -> tuple[bool, str]:
    """
    Activate a pack by copying its YAML files onto the live paths and
    clearing cached semantic singletons + dependent session_state keys
    so the app rebuilds its semantic context on the next rerun.

    Returns (success, message).
    """
    pack_dir = os.path.join(_PACKS_DIR, pack_id)
    model_path    = os.path.join(pack_dir, "semantic_model.yaml")
    glossary_path = os.path.join(pack_dir, "business_glossary.yaml")

    # The insurance PostgreSQL model has different physical tables and grains
    # from the lightweight CSV demo pack.
    try:
        from config.settings import get_data_config

        postgres_model = os.path.join(
            pack_dir, "semantic_model_postgres.yaml"
        )
        postgres_glossary = os.path.join(
            pack_dir, "business_glossary_postgres.yaml"
        )
        if (
            pack_id == "insurance"
            and get_data_config().get("backend") == "postgres"
            and os.path.isfile(postgres_model)
        ):
            model_path = postgres_model
            if os.path.isfile(postgres_glossary):
                glossary_path = postgres_glossary
    except Exception:
        pass

    if not (os.path.isfile(model_path) and os.path.isfile(glossary_path)):
        return False, f"Pack '{pack_id}' not found or incomplete."

    try:
        shutil.copyfile(model_path, _LIVE_MODEL_PATH)
        shutil.copyfile(glossary_path, _LIVE_GLOSSARY_PATH)
    except Exception as e:
        return False, f"Could not activate pack: {e}"

    _reset_semantic_singletons()

    # Clear the app's cached semantic objects / derived context so the
    # existing "if not in st.session_state" rebuild guards in app.py
    # re-populate them on the next run — these keys are all ones the
    # app already manages itself via st.session_state, so this is the
    # same pattern every other button in the app already uses.
    for key in (
        "semantic_loader",
        "semantic_search",
        "semantic_builder",
        "semantic_base_context",
        "semantic_column_map",
        "_pg_semantic_static",
        "last_glossary_matches",
        "last_glossary_hints",
    ):
        st.session_state.pop(key, None)

    # Drop session NLQ answer cache so prior pack SQL cannot be reused.
    try:
        memory = st.session_state.get("memory")
        if isinstance(memory, dict):
            memory.clear()
        else:
            st.session_state.memory = {}
    except Exception:
        pass

    st.session_state.industry_pack_id = pack_id
    return True, f"Activated '{pack_id}' pack."
