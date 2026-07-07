"""tokenwatch FastAPI application.

Wires together the transparent proxy, a JSON usage API, and a static dashboard.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import store
from .proxy import router as proxy_router

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init_db(os.environ.get("TOKENWATCH_DB", "tokenwatch.db"))
    yield


app = FastAPI(title="tokenwatch", description="Self-hosted LLM cost dashboard", lifespan=lifespan)
app.include_router(proxy_router)


@app.get("/api/usage")
def usage() -> JSONResponse:
    """Aggregated usage for the dashboard."""
    return JSONResponse(
        {
            "summary": store.summary(),
            "by_model": store.by_model(),
            "by_day": store.by_day(),
            "recent": store.recent(50),
        }
    )


@app.get("/")
def index() -> FileResponse:
    """Serve the single-page dashboard."""
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))


# Static assets (if any are added later) are served under /static.
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


def run() -> None:
    """Console-script entry point: launch uvicorn."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.environ.get("TOKENWATCH_HOST", "0.0.0.0"),
        port=int(os.environ.get("TOKENWATCH_PORT", "8000")),
    )
