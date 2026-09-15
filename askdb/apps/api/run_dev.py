"""Dev/server entrypoint that forces a SelectorEventLoop before Uvicorn serves.

Uvicorn 0.52 on Windows hard-codes ProactorEventLoop, which breaks psycopg async
(InterfaceError on every DB call while /health still returns 200).
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Ask DB API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=["app"] if args.reload else None,
        reload_excludes=[".venv", "__pycache__"] if args.reload else None,
        # Custom factory — required on Windows; harmless on other platforms.
        loop="app.windows_loop:selector_event_loop",
    )


if __name__ == "__main__":
    main()
