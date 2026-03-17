from collections import defaultdict, deque
from datetime import date


class MarketState:
    def __init__(self, maxlen: int = 500):
        self.closes = defaultdict(lambda: deque(maxlen=maxlen))
        self.volumes = defaultdict(lambda: deque(maxlen=maxlen))
        self.orderbooks = {}
        self.last_prices = {}
        self.cooldowns = {}
        self.daily_start_equity = {}
        self.daily_date = date.today()

    def reset_day_if_needed(self, equity: float):
        today = date.today()
        if today != self.daily_date:
            self.daily_date = today
            self.daily_start_equity = {"equity": equity}

    def set_daily_start_equity_once(self, equity: float):
        if "equity" not in self.daily_start_equity:
            self.daily_start_equity["equity"] = equity

    def update_candle(self, symbol: str, close: float, volume: float):
        self.closes[symbol].append(float(close))
        self.volumes[symbol].append(float(volume))
        self.last_prices[symbol] = float(close)

    def update_orderbook(self, symbol: str, snapshot: dict):
        self.orderbooks[symbol] = snapshot
        if snapshot["best_bid"] and snapshot["best_ask"]:
            self.last_prices[symbol] = (snapshot["best_bid"] + snapshot["best_ask"]) / 2

    def get_closes(self, symbol: str) -> list[float]:
        return list(self.closes[symbol])

    def get_volumes(self, symbol: str) -> list[float]:
        return list(self.volumes[symbol])

    def get_orderbook(self, symbol: str) -> dict | None:
        return self.orderbooks.get(symbol)

    def get_last_price(self, symbol: str) -> float | None:
        return self.last_prices.get(symbol)

    def in_cooldown(self, symbol: str, now_ts: float) -> bool:
        return self.cooldowns.get(symbol, 0) > now_ts

    def set_cooldown(self, symbol: str, until_ts: float):
        self.cooldowns[symbol] = until_ts
