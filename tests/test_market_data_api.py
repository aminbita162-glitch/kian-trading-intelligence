"""Tests for market-data API endpoints (Phase 03, AD-021).

Per Section 08.1: approved provider adapters with normalized schemas.
Per Addendum A11: OpenAPI/Swagger documentation alignment.
"""

import pytest
from fastapi.testclient import TestClient

from services.core.app import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


class TestMarketDataHealth:
    def test_market_data_health_returns_200(self, client: TestClient) -> None:
        response = client.get("/market-data/health")
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "simulated"
        assert data["connected"] is True
        assert "rate_limit_remaining" in data
        assert "stored_events" in data
        assert "freshness_max_age" in data


class TestTickerEndpoint:
    def test_get_ticker_returns_200(self, client: TestClient) -> None:
        response = client.get("/market-data/ticker/BTC/USDT")
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTC/USDT"
        assert float(data["last_price"]) > 0
        assert float(data["bid"]) > 0
        assert float(data["ask"]) > 0
        assert float(data["ask"]) >= float(data["bid"])

    def test_get_ticker_invalid_symbol(self, client: TestClient) -> None:
        response = client.get("/market-data/ticker/INVALID")
        assert response.status_code == 400
        assert "Invalid symbol format" in response.json()["detail"]

    def test_get_ticker_different_pair(self, client: TestClient) -> None:
        response = client.get("/market-data/ticker/ETH/USDT")
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "ETH/USDT"


class TestOrderBookEndpoint:
    def test_get_orderbook_returns_200(self, client: TestClient) -> None:
        response = client.get("/market-data/orderbook/BTC/USDT")
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTC/USDT"
        assert len(data["bids"]) == 10
        assert len(data["asks"]) == 10
        assert data["sequence"] > 0

    def test_get_orderbook_custom_depth(self, client: TestClient) -> None:
        response = client.get("/market-data/orderbook/BTC/USDT?depth=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["bids"]) == 5

    def test_get_orderbook_invalid_symbol(self, client: TestClient) -> None:
        response = client.get("/market-data/orderbook/NOSLASH")
        assert response.status_code == 400


class TestCandlesEndpoint:
    def test_get_candles_returns_200(self, client: TestClient) -> None:
        response = client.get("/market-data/candles/BTC/USDT?timeframe=1m&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 10
        for candle in data:
            assert candle["symbol"] == "BTC/USDT"
            assert float(candle["open"]) > 0
            assert float(candle["high"]) >= float(candle["open"])
            assert float(candle["low"]) <= float(candle["open"])
            assert float(candle["close"]) > 0

    def test_get_candles_invalid_timeframe(self, client: TestClient) -> None:
        response = client.get("/market-data/candles/BTC/USDT?timeframe=2m")
        assert response.status_code == 400
        assert "Invalid timeframe" in response.json()["detail"]

    def test_get_candles_invalid_symbol(self, client: TestClient) -> None:
        response = client.get("/market-data/candles/INVALID")
        assert response.status_code == 400

    def test_get_candles_limit_too_large(self, client: TestClient) -> None:
        response = client.get("/market-data/candles/BTC/USDT?limit=2000")
        assert response.status_code == 400
        assert "limit must be" in response.json()["detail"]

    def test_get_candles_limit_too_small(self, client: TestClient) -> None:
        response = client.get("/market-data/candles/BTC/USDT?limit=0")
        assert response.status_code == 400


class TestOpenAPISchema:
    def test_openapi_includes_market_data_endpoints(self, client: TestClient) -> None:
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        paths = schema["paths"]
        assert "/market-data/health" in paths
        assert "/market-data/ticker/{symbol_pair}" in paths
        assert "/market-data/orderbook/{symbol_pair}" in paths
        assert "/market-data/candles/{symbol_pair}" in paths
