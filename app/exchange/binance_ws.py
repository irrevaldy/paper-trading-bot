import asyncio
import json
import aiohttp
import requests

from app.config import settings
from app.market.orderbook import compute_orderbook_metrics


class BinanceWsExchange:
    def __init__(self):
        if settings.binance_use_testnet:
            self.rest_base = "https://testnet.binance.vision/api/v3"
            self.ws_base = "wss://stream.testnet.binance.vision/stream"
        else:
            self.rest_base = "https://api.binance.com/api/v3"
            self.ws_base = "wss://stream.binance.com:9443/stream"

    def _stream_names(self) -> list[str]:
        streams = []
        for symbol in settings.symbols:
            s = symbol.lower()
            streams.append(f"{s}@kline_1m")
            streams.append(f"{s}@depth{settings.orderbook_depth_levels}@100ms")
        return streams

    def _combined_stream_url(self) -> str:
        stream_path = "/".join(self._stream_names())
        return f"{self.ws_base}?streams={stream_path}"

    def _fetch_klines(self, symbol: str, limit: int = 150) -> list[dict]:
        url = f"{self.rest_base}/klines"
        params = {
            "symbol": symbol,
            "interval": "1m",
            "limit": limit,
        }
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        rows = response.json()

        candles = []
        for row in rows:
            candles.append({
                "open_time": row[0],
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
                "close_time": row[6],
            })
        return candles

    async def bootstrap(self, market_state, logger):
        for symbol in settings.symbols:
            candles = self._fetch_klines(symbol, limit=150)
            for c in candles:
                market_state.update_candle(symbol, c["close"], c["volume"])
            logger.info(f"Bootstrapped {len(candles)} candles for {symbol}")

    async def stream_forever(self, market_state, on_tick, logger):
        url = self._combined_stream_url()
        logger.info(f"Connecting websocket: {url}")

        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(
                        url,
                        heartbeat=30,
                        autoping=True,
                        receive_timeout=90,
                    ) as ws:
                        logger.info("WebSocket connected")

                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                payload = json.loads(msg.data)
                                stream = payload.get("stream", "")
                                data = payload.get("data", {})

                                handled = self._handle_message(market_state, stream, data, logger)
                                if handled:
                                    await on_tick()

                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                logger.warning("WebSocket error frame received")
                                break

                            elif msg.type in (
                                aiohttp.WSMsgType.CLOSED,
                                aiohttp.WSMsgType.CLOSE,
                            ):
                                logger.warning("WebSocket closed")
                                break

            except Exception as e:
                logger.exception(f"WebSocket loop error: {e}")

            logger.info("Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

    def _handle_message(self, market_state, stream: str, data: dict, logger) -> bool:
        if "@kline_" in stream:
            symbol = data.get("s")
            k = data.get("k", {})
            is_closed = k.get("x", False)
            if not symbol or not is_closed:
                return False

            close = float(k["c"])
            volume = float(k["v"])
            market_state.update_candle(symbol, close, volume)
            return True

        if "@depth" in stream:
            symbol = data.get("s")
            if not symbol:
                return False

            bids = [[float(p), float(q)] for p, q in data.get("b", [])]
            asks = [[float(p), float(q)] for p, q in data.get("a", [])]

            metrics = compute_orderbook_metrics(
                bids=bids,
                asks=asks,
                depth=settings.orderbook_depth_levels,
            )

            if metrics["avg_bid_qty"] > 0:
                metrics["suspicious_bid_wall"] = (
                    metrics["max_bid_qty"] >= metrics["avg_bid_qty"] * settings.wall_factor
                )
            if metrics["avg_ask_qty"] > 0:
                metrics["suspicious_ask_wall"] = (
                    metrics["max_ask_qty"] >= metrics["avg_ask_qty"] * settings.wall_factor
                )

            market_state.update_orderbook(symbol, metrics)
            return False

        return False
