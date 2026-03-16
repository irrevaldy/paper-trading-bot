from collections import defaultdict, deque


class MarketState:
    def __init__(self, maxlen: int = 300):
        self.closes = defaultdict(lambda: deque(maxlen=maxlen))
        self.volumes = defaultdict(lambda: deque(maxlen=maxlen))
        self.orderbooks = {}
        self.last_prices = {}
        self.last_signal_time = {}

    def update_candle(self, symbol: str, close: float, volume: float):
        self.closes[symbol].append(float(close))
        self.volumes[symbol].append(float(volume))
        self.last_prices[symbol] = float(close)

    def update_orderbook(self, symbol: str, snapshot: dict):
        self.orderbooks[symbol] = snapshot

    def get_closes(self, symbol: str) -> list[float]:
        return list(self.closes[symbol])

    def get_volumes(self, symbol: str) -> list[float]:
        return list(self.volumes[symbol])

    def get_orderbook(self, symbol: str) -> dict | None:
        return self.orderbooks.get(symbol)

    def get_last_price(self, symbol: str) -> float | None:
        return self.last_prices.get(symbol)
