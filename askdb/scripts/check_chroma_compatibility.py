"""Standalone Chroma smoke check; synthetic data, no app imports or API calls.

Run with an isolated Python environment containing chromadb. All index writes are
in a disposable temporary directory. Separate child processes test real reopen.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import platform
import socket
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def stage(action: str, path: str) -> None:
    # Prevent Python socket connections during this smoke test. This is a guard,
    # not an OS firewall: native-library network behavior needs separate review.
    def deny_connection(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Network connection blocked by offline compatibility check")

    socket.socket.connect = deny_connection  # type: ignore[method-assign]
    socket.socket.connect_ex = deny_connection  # type: ignore[method-assign]
    socket.create_connection = deny_connection  # type: ignore[assignment]

    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(
        path=path, settings=Settings(anonymized_telemetry=False)
    )
    if action == "write":
        collection = client.create_collection(
            "askme_compatibility",
            embedding_function=None,
            configuration={"hnsw": {"space": "cosine"}},
        )
        collection.upsert(
            ids=["west", "east"],
            embeddings=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            documents=["Synthetic West policy", "Synthetic East policy"],
            metadatas=[{"region": "West"}, {"region": "East"}],
        )
        require(collection.count() == 2, "Insert/count mismatch")
    else:
        collection = client.get_collection(
            "askme_compatibility", embedding_function=None
        )
        if action == "read":
            require(collection.count() == 2, "Persistence across processes failed")
            result = collection.query(
                query_embeddings=[[1.0, 0.0, 0.0]], n_results=1
            )
            require(result["ids"] == [["west"]], "Nearest-neighbor query failed")
            result = collection.query(
                query_embeddings=[[1.0, 0.0, 0.0]],
                where={"region": "East"},
                n_results=1,
            )
            require(result["ids"] == [["east"]], "Metadata filter failed")
            collection.delete(ids=["west"])
            require(collection.count() == 1, "Delete failed")
        else:
            require(collection.count() == 1, "Delete did not persist")
            require(collection.get(ids=["west"])["ids"] == [], "Deleted ID returned")
    print(f"PASS: {action}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["write", "read", "verify-delete"])
    parser.add_argument("--path")
    args = parser.parse_args()
    if args.stage:
        require(bool(args.path), "Stage requires --path")
        stage(args.stage, args.path)
        return 0

    print(f"Python: {platform.python_version()} | {platform.machine()}", flush=True)
    print(f"SQLite: {sqlite3.sqlite_version}", flush=True)
    try:
        print(f"Chroma: {importlib.metadata.version('chromadb')}", flush=True)
    except importlib.metadata.PackageNotFoundError:
        print("FAIL: chromadb is not installed in this Python environment.")
        return 1
    for package in ("onnxruntime", "tokenizers", "huggingface-hub", "torch", "sentence-transformers"):
        try:
            print(f"Dependency present: {package} {importlib.metadata.version(package)}")
        except importlib.metadata.PackageNotFoundError:
            pass

    with tempfile.TemporaryDirectory(prefix="askme-chroma-check-") as folder:
        for action in ("write", "read", "verify-delete"):
            subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--stage", action, "--path", folder],
                check=True,
                timeout=60,
            )
    print("PASS: local storage, query, filtering, restart and persistent delete.")
    print("No embedding model was configured; all vectors were supplied by this script.")
    print("This does not verify API access, RAG answer quality, scale or company approval.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
