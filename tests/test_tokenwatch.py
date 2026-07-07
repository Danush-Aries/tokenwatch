"""Offline test suite for tokenwatch. No real network calls are made."""

from __future__ import annotations

import importlib
import json

import httpx
import pytest
from fastapi.testclient import TestClient


# --------------------------------------------------------------------------- #
# Pricing
# --------------------------------------------------------------------------- #
def test_pricing_known_model():
    from app.pricing import cost_usd

    # gpt-4o: input 2.50 / output 10.00 per 1M tokens.
    cost = cost_usd("gpt-4o", 1_000_000, 1_000_000)
    assert cost == pytest.approx(2.50 + 10.00)


def test_pricing_partial_tokens():
    from app.pricing import cost_usd

    # 500k prompt + 250k completion on gpt-4o.
    cost = cost_usd("gpt-4o", 500_000, 250_000)
    assert cost == pytest.approx(0.5 * 2.50 + 0.25 * 10.00)


def test_pricing_fallback_flagged():
    from app.pricing import cost_detail, cost_usd

    detail = cost_detail("totally-unknown-model", 1_000_000, 1_000_000)
    assert detail.fallback is True
    # _default: input 1.00 / output 3.00.
    assert detail.cost_usd == pytest.approx(1.00 + 3.00)

    known = cost_detail("gpt-4o", 10, 10)
    assert known.fallback is False
    assert cost_usd("gpt-4o", 0, 0) == 0.0


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #
@pytest.fixture()
def temp_store(tmp_path):
    from app import store

    db = tmp_path / "test.db"
    store.init_db(str(db))
    return store


def test_store_roundtrip(temp_store):
    store = temp_store

    # Two rows, same day, different models.
    day = 1_700_000_000.0  # fixed epoch → deterministic date bucket
    store.record("gpt-4o", 1000, 500, 0.02, 120.0, 200, ts=day)
    store.record("claude-sonnet-4-6", 2000, 1000, 0.03, 200.0, 200, ts=day)

    s = store.summary()
    assert s["count"] == 2
    assert s["total_tokens"] == 1000 + 500 + 2000 + 1000
    assert s["total_cost_usd"] == pytest.approx(0.05)

    models = {r["model"]: r for r in store.by_model()}
    assert models["gpt-4o"]["count"] == 1
    assert models["gpt-4o"]["total_tokens"] == 1500
    assert models["claude-sonnet-4-6"]["cost_usd"] == pytest.approx(0.03)

    days = store.by_day()
    assert len(days) == 1
    assert days[0]["count"] == 2
    assert days[0]["cost_usd"] == pytest.approx(0.05)

    recent = store.recent(10)
    assert len(recent) == 2
    # Newest first: last inserted row leads.
    assert recent[0]["model"] == "claude-sonnet-4-6"


# --------------------------------------------------------------------------- #
# Proxy + API (fake upstream via httpx.MockTransport)
# --------------------------------------------------------------------------- #
@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A TestClient with an isolated DB and a faked httpx upstream."""
    from app import store

    db = tmp_path / "proxy.db"
    # The app's lifespan re-inits the DB from this env var on startup, so it must
    # point at the isolated temp file for the whole client session.
    monkeypatch.setenv("TOKENWATCH_DB", str(db))
    store.init_db(str(db))

    def handler(request: httpx.Request) -> httpx.Response:
        # Simulate the Anthropic Messages API response shape.
        return httpx.Response(
            200,
            json={
                "id": "msg_123",
                "type": "message",
                "model": "claude-sonnet-4-6",
                "content": [{"type": "text", "text": "hi"}],
                "usage": {"input_tokens": 1000, "output_tokens": 500},
            },
        )

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    # Patch the AsyncClient used inside proxy.py.
    import app.proxy as proxy_mod

    monkeypatch.setattr(proxy_mod.httpx, "AsyncClient", fake_async_client)

    from app.main import app

    with TestClient(app) as c:
        yield c


def test_proxy_records_and_returns_upstream(client):
    resp = client.post(
        "/v1/messages",
        headers={"x-api-key": "fake", "anthropic-version": "2023-06-01"},
        content=json.dumps({"model": "claude-sonnet-4-6", "messages": []}),
    )
    assert resp.status_code == 200
    # Upstream body is returned unchanged.
    assert resp.json()["id"] == "msg_123"

    # A row was recorded with the correct cost.
    from app import store

    recent = store.recent(1)
    assert len(recent) == 1
    row = recent[0]
    assert row["model"] == "claude-sonnet-4-6"
    assert row["prompt_tokens"] == 1000
    assert row["completion_tokens"] == 500
    assert row["status"] == 200
    # claude-sonnet-4-6: input 3.00 / output 15.00 per 1M.
    expected = (1000 / 1e6) * 3.00 + (500 / 1e6) * 15.00
    assert row["cost_usd"] == pytest.approx(expected)


def test_api_usage_reflects_recorded_row(client):
    client.post(
        "/v1/messages",
        content=json.dumps({"model": "claude-sonnet-4-6", "messages": []}),
    )
    resp = client.get("/api/usage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["count"] == 1
    assert data["summary"]["total_tokens"] == 1500
    assert any(m["model"] == "claude-sonnet-4-6" for m in data["by_model"])
    assert len(data["recent"]) == 1
