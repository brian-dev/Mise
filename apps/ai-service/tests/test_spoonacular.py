"""Spoonacular provider + the resolve_prices seam.

Offline tests stub the HTTP / AI calls; one opt-in `live` test hits the real
Spoonacular API (consumes a point — deselected by default)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

import mise_ai.pricing as pricing_mod
import mise_ai.spoonacular as sp_mod
from mise_ai.anthropic_client import ToolCallResult, Usage
from mise_ai.config import settings
from mise_ai.pricing import PricingItem, resolve_prices
from mise_ai.spoonacular import spoonacular_prices


class _FakeResp:
    def __init__(self, status: int, payload: Any) -> None:
        self.status_code = status
        self._payload = payload

    def json(self) -> Any:
        return self._payload


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    sp_mod._CACHE.clear()


def test_spoonacular_parses_costs(monkeypatch) -> None:
    monkeypatch.setattr(settings, "spoonacular_api_key", "test-key")
    payload = [
        {"name": "onion", "estimatedCost": {"value": 199.58, "unit": "cents"}},
        {"name": "garlic", "estimatedCost": {"value": 20.0, "unit": "cents"}},
    ]
    monkeypatch.setattr(sp_mod.httpx, "post", lambda *a, **k: _FakeResp(200, payload))
    out = spoonacular_prices(
        [PricingItem("onion", Decimal("2"), "lb"), PricingItem("garlic", Decimal("3"), "clove")]
    )
    assert out == [Decimal("2.00"), Decimal("0.20")]


def test_spoonacular_unrecognized_is_none(monkeypatch) -> None:
    monkeypatch.setattr(settings, "spoonacular_api_key", "test-key")
    payload = [{"name": "", "estimatedCost": None}]  # not recognized
    monkeypatch.setattr(sp_mod.httpx, "post", lambda *a, **k: _FakeResp(200, payload))
    assert spoonacular_prices([PricingItem("zzz", Decimal("1"), "unit")]) == [None]


def test_spoonacular_http_error_all_none(monkeypatch) -> None:
    monkeypatch.setattr(settings, "spoonacular_api_key", "test-key")
    monkeypatch.setattr(sp_mod.httpx, "post", lambda *a, **k: _FakeResp(402, "quota"))
    assert spoonacular_prices([PricingItem("onion", Decimal("2"), "lb")]) == [None]


def test_no_key_returns_none(monkeypatch) -> None:
    monkeypatch.setattr(settings, "spoonacular_api_key", "")
    assert spoonacular_prices([PricingItem("onion", Decimal("2"), "lb")]) == [None]


def _stub_ai(monkeypatch, prices: list[float]) -> None:
    def fake_call_tool(**_kw: object) -> ToolCallResult:
        return ToolCallResult(
            tool_input={"prices": [{"estimated_price": p} for p in prices]},
            usage=Usage(1, 1, 0, 0),
            raw_content=[],
        )

    monkeypatch.setattr(pricing_mod, "call_tool", fake_call_tool)


def test_resolve_free_tier_uses_ai(monkeypatch) -> None:
    monkeypatch.setattr(settings, "spoonacular_api_key", "")
    _stub_ai(monkeypatch, [1.0, 2.0])
    res = resolve_prices([PricingItem("a", Decimal("1"), "unit"),
                          PricingItem("b", Decimal("1"), "unit")])
    assert res.prices == [Decimal("1.00"), Decimal("2.00")]
    assert res.sources == ["ai", "ai"]


def test_resolve_paid_tier_spoonacular_then_ai(monkeypatch) -> None:
    monkeypatch.setattr(settings, "spoonacular_api_key", "test-key")
    # resolve_prices does `from .spoonacular import spoonacular_prices` at call
    # time, so patch the module attribute. Spoonacular prices #1, misses #2.
    monkeypatch.setattr(sp_mod, "spoonacular_prices", lambda items: [Decimal("3.00"), None])
    _stub_ai(monkeypatch, [0.50])  # AI fills the one miss
    res = resolve_prices([PricingItem("onion", Decimal("2"), "lb"),
                          PricingItem("zzz", Decimal("1"), "unit")])
    assert res.prices == [Decimal("3.00"), Decimal("0.50")]
    assert res.sources == ["spoonacular", "ai"]


@pytest.mark.live
def test_live_spoonacular() -> None:
    if not settings.spoonacular_api_key:
        pytest.skip("no SPOONACULAR_API_KEY")
    out = spoonacular_prices([PricingItem("yellow onion", Decimal("2"), "lb")])
    assert out[0] is not None and out[0] > 0
