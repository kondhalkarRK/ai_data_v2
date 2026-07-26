# scaffold_project.py
"""
Run once to create the full folder structure with empty/stub files.
Does NOT touch your existing app.py — creates everything alongside it.
"""
import os

STRUCTURE = {
    "config": ["__init__.py", "settings.py", "styles.py", "constants.py"],
    "core": [
        "__init__.py", "llm_client.py", "sql_guardrails.py", "nlq_engine.py",
        "schema_builder.py", "join_engine.py", "chart_engine.py",
        "analysis_engine.py", "kpi_engine.py", "data_quality_engine.py", "utils.py"
    ],
    "features": ["__init__.py"],
    "features/materialized_views": [
        "__init__.py", "view_store.py", "view_manager.py", "view_triggers.py"
    ],
    "features/rag_query_memory": [
        "__init__.py", "vector_store.py", "embedder.py",
        "query_memory.py", "glossary_store.py"
    ],
    "features/vector_schema_retrieval": [
        "__init__.py", "schema_indexer.py", "schema_retriever.py"
    ],
    "ui": [
        "__init__.py", "sidebar.py", "tab_join.py",
        "tab_preview.py", "tab_kpi.py", "tab_query.py"
    ],
    "rag_storage/chroma_db": [],
    "rag_storage/materialized_cache": [],
}

STUB_HEADER = '''"""
{path}
Auto-generated stub — implement per Cursor prompt instructions.
DO NOT modify existing app.py logic when filling this in.
"""

'''

def scaffold():
    for folder, files in STRUCTURE.items():
        os.makedirs(folder, exist_ok=True)
        for f in files:
            filepath = os.path.join(folder, f)
            if not os.path.exists(filepath):
                with open(filepath, "w") as fh:
                    if f.endswith(".py") and f != "__init__.py":
                        fh.write(STUB_HEADER.format(path=filepath))
                print(f"✅ Created: {filepath}")
            else:
                print(f"⏭️  Skipped (exists): {filepath}")

    # .gitignore additions
    gitignore_additions = "\nrag_storage/\n"
    with open(".gitignore", "a") as f:
        f.write(gitignore_additions)
    print("\n✅ Folder structure scaffolded successfully.")
    print("📁 Your existing app.py is untouched.")

if __name__ == "__main__":
    scaffold()