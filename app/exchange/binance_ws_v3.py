import asyncio
import json
import aiohttp
import requests

from app.config import settings
from app.exchange.local_orderbook import LocalOrderBook
from app.market.orderbook import compute_orderbook_metrics


class BinanceWsV3Exchange:
    def __init__(self):
        if settings.binance_use_testnet:
            self.rest_base = "https://testnet.binance.vision/api/v3"
            self.ws_base = "wss://stream.testnet.binance.vision/stream"
        else:
            self.rest_base = "https://api.binance.com/api/v3"
            self.ws_base = "wss://stream.binance.com:9443/stream"

        self.orderbooks = {symbol: LocalOrderBook(symbol) for symbol in settings.symbols}

    def _stream_names(self) -> list[str]:
        streams = []
        for symbol in settings.symbols:
            s = symbol.lower()
            streams.append(f"{s}@kline_1m")
            streams.append(f"{s}@depth@100ms")
        return streams

    def _combined_stream_url(self) -> str:
        return f"{self.ws_base}?streams={'/'.join(self._stream_names())}"

    def _fetch_klines(self, symbol: str, limit: int = 150) -> list[dict]:
        response = requests.get(
            f"{self.rest_base}/klines",
            params={"symbol": symbol, "interval": "1m", "limit": limit},
            timeout=15,
        )
        response.raise_for_status()
        rows = response.json()

        candles = []
        for row in rows:
            candles.append({
                "close": float(row[4]),
                "volume": float(row[5]),
            })
        return candles

    def _fetch_depth_snapshot(self, symbol: str, limit: int = 1000) -> dict:
        response = requests.get(
            f"{self.rest_base}/depth",
            params={"symbol": symbol, "limit": limit},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    async def bootstrap(self, market_state, logger):
        for symbol in settings.symbols:
            candles = self._fetch_klines(symbol, limit=150)
            for c in candles:
                market_state.update_candle(symbol, c["close"], c["volume"])
            logger.info(f"Bootstrapped {len(candles)} candles for {symbol}")

    async def load_orderbook_snapshots(self, logger):
        for symbol in settings.symbols:
            snapshot = self._fetch_depth_snapshot(symbol, limit=1000)
            ob = self.orderbooks[symbol]
            ob.load_snapshot(snapshot)
            ob.apply_buffered_events()
            logger.info(f"Loaded order book snapshot for {symbol} lastUpdateId={ob.last_update_id}")

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

                        snapshot_loaded = False

                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                payload = json.loads(msg.data)
                                stream = payload.get("stream", "")
                                data = payload.get("data", {})

                                if "@depth" in stream:
                                    symbol = data.get("s")
                                    if symbol:
                                        self.orderbooks[symbol].buffer_event(data)

                                        if not snapshot_loaded:
                                            await self.load_orderbook_snapshots(logger)
                                            snapshot_loaded = True

                                        self._handle_depth(symbol, market_state)

                                elif "@kline_" in stream:
                                    handled = self._handle_kline(data, market_state)
                                    if handled:
                                        await on_tick()

                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE):
                                logger.warning("WebSocket closed")
                                break

                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                logger.warning("WebSocket error frame received")
                                break

            except Exception as e:
                logger.exception(f"WebSocket loop error: {e}")

            logger.info("Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

    def _handle_kline(self, data: dict, market_state) -> bool:
        symbol = data.get("s")
        k = data.get("k", {})
        is_closed = k.get("x", False)

        if not symbol or not is_closed:
            return False

        close = float(k["c"])
        volume = float(k["v"])
        market_state.update_candle(symbol, close, volume)
        return True

    def _handle_depth(self, symbol: str, market_state):
        ob = self.orderbooks[symbol]
        if not ob.snapshot_loaded:
            return

        event = ob.buffer[-1] if ob.buffer else None
        if event:
            try:
                ob.apply_event(event)
                ob.buffer = []
            except RuntimeError:
                ob.snapshot_loaded = False
                return

        bids = ob.top_n_bids(settings.orderbook_depth_levels)
        asks = ob.top_n_asks(settings.orderbook_depth_levels)

        metrics = compute_orderbook_metrics(
            bids=bids,
            asks=asks,
            depth=settings.orderbook_depth_levels,
            wall_factor=settings.wall_factor,
        )
        market_state.update_orderbook(symbol, metrics)
