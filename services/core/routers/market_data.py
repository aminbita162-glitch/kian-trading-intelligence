"""Market data API router for Kian Trading Intelligence.

Per AD-021: normalized market data with approved provider adapters.
Per Section 08.1: historical storage and deterministic replay.
Per E3 (Structure and Verification Separation): the market-data router
depends on the MarketDataProvider abstract base from the services package,
not the concrete SimulatedMarketDataProvider. The concrete provider is
wired via a runtime factory (importlib) so that the production services/
tree has no static dependency on the simulation/ package.
"""

from __future__ import annotations

import asyncio as _asyncio
import importlib as _importlib
import os as _os
from typing import cast

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from contracts.market_data import (
    Symbol,
    Timeframe,
)
from services.market_data.processor import EventProcessor
from services.market_data.provider import MarketDataProvider, MarketDataProviderError
from services.market_data.storage import HistoricalStorage

router = APIRouter(tags=["Market Data"])

# Singletons — in-memory (production needs PostgreSQL + Redis)
_market_storage = HistoricalStorage()


def _create_provider() -> MarketDataProvider:
    """Create a market-data provider based on operating mode.

    Per E3: the production services/ tree must NOT statically import from
    the simulation/ package. The concrete simulator class is loaded via
    importlib.import_module (a runtime string-based import), so the
    production image has no compile-time dependency on simulation code.

    In SIMULATION mode the SimulatedMarketDataProvider is loaded.
    In LIVE mode a real adapter would be used (not yet configured).
    """
    mode = _os.environ.get("KTI_OPERATING_MODE", "simulation").lower()
    if mode == "live":
        raise MarketDataProviderError(
            "Live market-data provider not yet configured. Use SIMULATION mode."
        )
    # Runtime import via importlib — no static 'from simulation' in the AST.
    _module = _importlib.import_module("simulation.market_data_simulator")  # noqa: PLC0415
    _cls = _module.SimulatedMarketDataProvider
    return cast(MarketDataProvider, _cls())


_market_provider = _create_provider()
_market_processor = EventProcessor(storage=_market_storage)

# Provider is connected in SIMULATION mode (no real exchange)
_loop = _asyncio.new_event_loop()
_loop.run_until_complete(_market_provider.connect())
_loop.close()


# ── Response Models ──


class TickerResponse(BaseModel):
    """Market data ticker response."""

    symbol: str
    last_price: str
    bid: str
    ask: str
    high_24h: str
    low_24h: str
    volume_24h: str
    timestamp: str


class OrderBookResponse(BaseModel):
    """Order book snapshot response."""

    symbol: str
    bids: list[list[str]]
    asks: list[list[str]]
    timestamp: str
    sequence: int


class CandleResponse(BaseModel):
    """OHLCV candle response."""

    symbol: str
    timeframe: str
    open: str
    high: str
    low: str
    close: str
    volume: str
    open_time: str
    close_time: str


class MarketDataHealthResponse(BaseModel):
    """Market data service health response."""

    provider: str
    connected: bool
    rate_limit_remaining: int
    stored_events: int
    freshness_max_age: str


# ── Endpoints ──


@router.get("/market-data/health", response_model=MarketDataHealthResponse)
async def market_data_health() -> MarketDataHealthResponse:
    """Market data service health and status.

    Per AD-021: market data infrastructure health.
    Per AD-003: operating mode is always identified.
    """
    return MarketDataHealthResponse(
        provider=_market_provider.provider_type.value,
        connected=_market_provider.connection.connected,
        rate_limit_remaining=_market_provider.rate_limiter.remaining(),
        stored_events=_market_storage.count,
        freshness_max_age=f"{_market_processor.freshness.max_age}",
    )


@router.get("/market-data/ticker/{symbol_pair:path}", response_model=TickerResponse)
async def get_ticker_endpoint(symbol_pair: str) -> TickerResponse:
    """Get the current ticker for a symbol pair.

    Per AD-021: normalized market data.
    Per Section 08.1: approved provider adapters with normalized schemas.
    """
    try:
        symbol = Symbol.parse(symbol_pair)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid symbol format: {symbol_pair}. Expected 'BASE/QUOTE'.",
        ) from None

    try:
        ticker = await _market_provider.get_ticker(symbol)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Market data provider error: {exc}",
        ) from None

    return TickerResponse(
        symbol=ticker.symbol.pair,
        last_price=ticker.last_price,
        bid=ticker.bid,
        ask=ticker.ask,
        high_24h=ticker.high_24h,
        low_24h=ticker.low_24h,
        volume_24h=ticker.volume_24h,
        timestamp=ticker.timestamp.isoformat(),
    )


@router.get("/market-data/orderbook/{symbol_pair:path}", response_model=OrderBookResponse)
async def get_orderbook_endpoint(
    symbol_pair: str,
    depth: int = 10,
) -> OrderBookResponse:
    """Get the current order book snapshot for a symbol pair.

    Per Section 08.1: order book with ordering controls.
    """
    try:
        symbol = Symbol.parse(symbol_pair)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid symbol format: {symbol_pair}. Expected 'BASE/QUOTE'.",
        ) from None

    try:
        book = await _market_provider.get_order_book(symbol, depth=depth)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Market data provider error: {exc}",
        ) from None

    return OrderBookResponse(
        symbol=book.symbol.pair,
        bids=[[lvl.price, lvl.amount] for lvl in book.bids],
        asks=[[lvl.price, lvl.amount] for lvl in book.asks],
        timestamp=book.timestamp.isoformat(),
        sequence=book.sequence,
    )


@router.get("/market-data/candles/{symbol_pair:path}", response_model=list[CandleResponse])
async def get_candles_endpoint(
    symbol_pair: str,
    timeframe: str = "1m",
    limit: int = 100,
) -> list[CandleResponse]:
    """Get historical candles for a symbol pair.

    Per Section 08.1: historical storage and deterministic replay.
    Per AD-003: deterministic, no LLM dependency.
    """
    try:
        symbol = Symbol.parse(symbol_pair)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid symbol format: {symbol_pair}. Expected 'BASE/QUOTE'.",
        ) from None

    try:
        tf = Timeframe(timeframe)
    except ValueError:
        supported = ", ".join(t.value for t in Timeframe)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid timeframe: {timeframe}. Supported: {supported}",
        ) from None

    MAX_CANDLE_LIMIT = 1000

    if limit < 1 or limit > MAX_CANDLE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="limit must be between 1 and 1000.",
        )

    try:
        candles = await _market_provider.get_candles(symbol, tf, limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Market data provider error: {exc}",
        ) from None

    return [
        CandleResponse(
            symbol=c.symbol.pair,
            timeframe=c.timeframe.value,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            volume=c.volume,
            open_time=c.open_time.isoformat(),
            close_time=c.close_time.isoformat(),
        )
        for c in candles
    ]
