import asyncio
import json
import time

import aiohttp
import requests

from app.config import settings
from app.exchange.base import BaseExchange
from app.market.orderbook import compute_orderbook_metrics

# Static JWT required by Indodax public market data WebSocket
_WS_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJleHAiOjE5NDY2MTg0MTV9"
    ".UR1lBM6Eqh0yWz-PVirw1uPCxe60FdchR8eNVdsskeo"
)


class IndodaxWsExchange(BaseExchange):
    REST_BASE = "https://indodax.com"
    WS_URL = "wss://ws3.indodax.com/ws/"

    def __init__(self):
        self._channel_to_symbol: dict[str, str] = {}
        self._rebuild_channel_map()

    def _rebuild_channel_map(self):
        self._channel_to_symbol = {}
        for symbol in settings.symbols:
            pair_id = self._pair_id(symbol)
            self._channel_to_symbol[f"market:order-book-{pair_id}"] = symbol
            self._channel_to_symbol[f"chart:tick-{pair_id}"] = symbol
            self._channel_to_symbol[f"market:trade-activity-{pair_id}"] = symbol

    # ─────────────────────────────────────────────
    # Symbol helpers
    # ─────────────────────────────────────────────

    @staticmethod
    def _pair_id(symbol: str) -> str:
        """btc_idr → btcidr"""
        return symbol.replace("_", "").lower()

    @staticmethod
    def _base(symbol: str) -> str:
        """btc_idr → btc"""
        return symbol.split("_")[0].lower()

    # ─────────────────────────────────────────────
    # Public REST: symbol discovery
    # ─────────────────────────────────────────────

    @staticmethod
    def fetch_active_pairs(n: int = 20) -> list[str]:
        """Return top N IDR pairs ranked by 24h IDR volume."""
        # Build id→symbol map from pairs list
        pairs_resp = requests.get(f"https://indodax.com/api/pairs", timeout=15)
        pairs_resp.raise_for_status()
        id_to_symbol: dict[str, str] = {}
        for p in pairs_resp.json():
            pid = p.get("id", "").lower().replace("_", "")
            traded = p.get("traded_currency", "").lower()
            base = p.get("base_currency", "").lower()
            if pid and traded and base:
                id_to_symbol[pid] = f"{traded}_{base}"

        # Rank by 24h IDR volume from summaries
        summaries_resp = requests.get(f"https://indodax.com/api/summaries", timeout=15)
        summaries_resp.raise_for_status()
        tickers = summaries_resp.json().get("tickers", {})

        idr_pairs: list[tuple[str, float]] = []
        for pid, ticker in tickers.items():
            pid_norm = pid.lower().replace("_", "")
            symbol = id_to_symbol.get(pid_norm)
            if not symbol or not symbol.endswith("_idr"):
                continue
            vol = float(ticker.get("vol_idr", 0) or 0)
            idr_pairs.append((symbol, vol))

        idr_pairs.sort(key=lambda x: x[1], reverse=True)
        return [sym for sym, _ in idr_pairs[:n]]

    # ─────────────────────────────────────────────
    # REST bootstrap
    # ─────────────────────────────────────────────

    def _fetch_klines(self, symbol: str, limit: int = 150) -> list[dict]:
        now = int(time.time())
        from_ts = now - limit * 60
        resp = requests.get(
            f"{self.REST_BASE}/tradingview/history_v2",
            params={
                "symbol": self._pair_id(symbol).upper(),
                "tf": "1",
                "from": from_ts,
                "to": now,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    # ─────────────────────────────────────────────
    # Order book parsing
    # ─────────────────────────────────────────────

    def _parse_ob_side(self, entries: list[dict], base: str) -> list[list[float]]:
        vol_key = f"{base}_volume"
        result = []
        for e in entries:
            try:
                price = float(e["price"])
                qty = float(e.get(vol_key) or e.get("crypto_volume") or 0)
                if price > 0 and qty > 0:
                    result.append([price, qty])
            except (KeyError, ValueError, TypeError):
                continue
        return result

    # ─────────────────────────────────────────────
    # Message extraction
    # ─────────────────────────────────────────────

    def _extract_push(self, payload: dict) -> tuple[str | None, object]:
        result = payload.get("result")
        if not isinstance(result, dict):
            return None, None

        channel = result.get("channel")
        data = result.get("data")

        # Unwrap double-nested data if present
        if isinstance(data, dict) and "data" in data and not (
            "asks" in data or "price" in data or "close" in data
        ):
            data = data["data"]

        if channel and data is not None:
            return channel, data

        return None, None

    # ─────────────────────────────────────────────
    # Tick handlers
    # ─────────────────────────────────────────────

    def _handle_orderbook(self, symbol: str, data, market_state):
        ob = data[-1] if isinstance(data, list) else data
        if not isinstance(ob, dict):
            return

        base = self._base(symbol)
        bids = self._parse_ob_side(ob.get("bids", []), base)
        asks = self._parse_ob_side(ob.get("asks", []), base)

        if not bids or not asks:
            return

        metrics = compute_orderbook_metrics(
            bids=bids,
            asks=asks,
            depth=settings.orderbook_depth_levels,
            wall_factor=settings.wall_factor,
        )
        market_state.update_orderbook(symbol, metrics)

    def _handle_chart_tick(self, symbol: str, data, market_state) -> bool:
        """1m candle from chart:tick. data may be a list or a single dict.
        Returns True → caller fires on_tick."""
        ticks = data if isinstance(data, list) else [data]
        fired = False
        for tick in ticks:
            if not isinstance(tick, dict):
                continue
            try:
                close = float(tick.get("close", 0))
                volume = float(tick.get("volume", 0))
            except (TypeError, ValueError):
                continue
            if close:
                market_state.update_candle(symbol, close, volume)
                fired = True
        return fired

    def _handle_trade(self, symbol: str, data, market_state):
        """Update last price from trade activity. data may be a list or a single dict."""
        trades = data if isinstance(data, list) else [data]
        for trade in trades:
            if not isinstance(trade, dict):
                continue
            try:
                price = float(trade.get("price", 0))
            except (TypeError, ValueError):
                continue
            if price:
                market_state.last_prices[symbol] = price

    # ─────────────────────────────────────────────
    # BaseExchange interface
    # ─────────────────────────────────────────────

    async def bootstrap(self, market_state, logger):
        for symbol in settings.symbols:
            try:
                candles = self._fetch_klines(symbol, limit=150)
                for c in candles:
                    market_state.update_candle(symbol, float(c["Close"]), float(c["Volume"]))
                logger.info(f"Bootstrapped {len(candles)} candles for {symbol}")
            except Exception as e:
                logger.warning(f"Bootstrap failed for {symbol}: {e}")

    async def stream_forever(self, market_state, on_tick, logger):
        while True:
            try:
                await self._run_ws(market_state, on_tick, logger)
            except Exception as e:
                logger.exception(f"WebSocket loop error: {e}")
            logger.info("Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

    async def _run_ws(self, market_state, on_tick, logger):
        logger.info(f"Connecting to Indodax WebSocket: {self.WS_URL}")

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                self.WS_URL,
                heartbeat=30,
                autoping=True,
                receive_timeout=90,
            ) as ws:
                logger.info("Indodax WebSocket connected")

                # Connect — static JWT, no "method" field
                await ws.send_json({"params": {"token": _WS_TOKEN}, "id": 1})

                # Subscribe — method: 1
                req_id = 2
                for symbol in settings.symbols:
                    pair_id = self._pair_id(symbol)
                    for channel in (
                        f"market:order-book-{pair_id}",
                        f"chart:tick-{pair_id}",
                        f"market:trade-activity-{pair_id}",
                    ):
                        await ws.send_json({
                            "method": 1,
                            "params": {"channel": channel},
                            "id": req_id,
                        })
                        req_id += 1

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            payload = json.loads(msg.data)
                        except json.JSONDecodeError:
                            continue

                        channel, data = self._extract_push(payload)
                        if not channel or data is None:
                            continue

                        symbol = self._channel_to_symbol.get(channel)
                        if not symbol:
                            continue

                        if "order-book" in channel:
                            self._handle_orderbook(symbol, data, market_state)

                        elif "chart:tick" in channel:
                            if self._handle_chart_tick(symbol, data, market_state):
                                await on_tick()

                        elif "trade-activity" in channel:
                            self._handle_trade(symbol, data, market_state)

                    elif msg.type in (
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.ERROR,
                    ):
                        logger.warning(f"WebSocket closed: {msg.type}")
                        break
