from __future__ import annotations

import uvicorn

from .settings import APISettings


def main() -> None:
    settings = APISettings.load()
    # One worker retains the process-local CLIP model, feedback contexts, and
    # rate limits. Multi-worker deployment needs shared limits/context storage.
    uvicorn.run("src.api.app:app", host=settings.host, port=settings.port, workers=1)


if __name__ == "__main__":
    main()
