"""One bounded provider diagnostic using environment settings, without database writes."""

import asyncio
import json
import time

from app import compat  # noqa: F401
from app.core.config import Settings
from app.services.llm import complete_text, llm_configured


async def main() -> None:
    settings = Settings()
    if not llm_configured(settings):
        print(json.dumps({"configured_from_environment": False, "live_verified": False}))
        return
    started = time.perf_counter()
    try:
        async with asyncio.timeout(12):
            result = await complete_text(
                settings=settings,
                system="Return only JSON.",
                user='Return {"status":"ok"}.',
                max_tokens=32,
            )
        print(
            json.dumps(
                {
                    "configured_from_environment": True,
                    "live_verified": bool(result.content and not result.error),
                    "elapsed_ms": round((time.perf_counter() - started) * 1000),
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                }
            )
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "configured_from_environment": True,
                    "live_verified": False,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000),
                    "error_type": type(exc).__name__,
                }
            )
        )


asyncio.run(main())
