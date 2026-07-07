"""Transparent proxy router for Anthropic and OpenAI chat endpoints.

Requests are forwarded verbatim to the configured upstream, the ``usage`` block
is parsed from the response, cost is computed, and a row is recorded to SQLite.
The upstream response (including errors) is returned unchanged so the proxy is a
drop-in base URL replacement.
"""

from __future__ import annotations

import os
import time

import httpx
from fastapi import APIRouter, Request, Response

from . import store
from .pricing import cost_usd

router = APIRouter()

# Headers we must not forward: they describe the hop to tokenwatch, not upstream.
_HOP_BY_HOP = {
    "host",
    "content-length",
    "connection",
    "keep-alive",
    "transfer-encoding",
    "accept-encoding",
}


def _upstream_anthropic() -> str:
    return os.environ.get(
        "TOKENWATCH_UPSTREAM_ANTHROPIC", "https://api.anthropic.com"
    ).rstrip("/")


def _upstream_openai() -> str:
    return os.environ.get(
        "TOKENWATCH_UPSTREAM_OPENAI", "https://api.openai.com"
    ).rstrip("/")


def _forward_headers(request: Request) -> dict[str, str]:
    """Copy client headers, dropping hop-by-hop ones so auth passes through."""
    return {
        k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP
    }


async def _proxy(request: Request, base_url: str, path: str, flavor: str) -> Response:
    body = await request.body()
    headers = _forward_headers(request)
    url = f"{base_url}{path}"

    started = time.perf_counter()
    status = 0
    upstream_body = b""
    upstream_headers: dict[str, str] = {}
    media_type = "application/json"
    payload: dict = {}

    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            resp = await client.request(
                request.method, url, content=body, headers=headers
            )
        status = resp.status_code
        upstream_body = resp.content
        media_type = resp.headers.get("content-type", "application/json")
        # Preserve everything except hop-by-hop/length headers we cannot honor.
        upstream_headers = {
            k: v
            for k, v in resp.headers.items()
            if k.lower() not in _HOP_BY_HOP | {"content-type"}
        }
        try:
            payload = resp.json()
        except Exception:
            payload = {}
    except httpx.HTTPError as exc:
        status = 502
        payload = {"error": {"type": "upstream_error", "message": str(exc)}}
        import json

        upstream_body = json.dumps(payload).encode()

    latency_ms = (time.perf_counter() - started) * 1000.0

    _record(payload, flavor, request, latency_ms, status)

    return Response(
        content=upstream_body,
        status_code=status,
        headers=upstream_headers,
        media_type=media_type,
    )


def _record(
    payload: dict, flavor: str, request: Request, latency_ms: float, status: int
) -> None:
    """Extract usage + model from a response payload and persist a row."""
    usage = payload.get("usage") or {}
    if flavor == "anthropic":
        prompt = int(usage.get("input_tokens", 0) or 0)
        completion = int(usage.get("output_tokens", 0) or 0)
    else:  # openai
        prompt = int(usage.get("prompt_tokens", 0) or 0)
        completion = int(usage.get("completion_tokens", 0) or 0)

    model = payload.get("model") or "unknown"
    cost = cost_usd(model, prompt, completion)

    store.record(
        model=model,
        prompt_tokens=prompt,
        completion_tokens=completion,
        cost_usd=cost,
        latency_ms=latency_ms,
        status=status,
    )


@router.post("/v1/messages")
async def messages(request: Request) -> Response:
    """Anthropic-shaped proxy endpoint."""
    return await _proxy(request, _upstream_anthropic(), "/v1/messages", "anthropic")


@router.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Response:
    """OpenAI-shaped proxy endpoint."""
    return await _proxy(
        request, _upstream_openai(), "/v1/chat/completions", "openai"
    )
