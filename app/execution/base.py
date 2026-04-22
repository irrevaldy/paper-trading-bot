from abc import ABC, abstractmethod


class BaseExecutor(ABC):
    @abstractmethod
    def buy(self, symbol: str, price: float, reason: str, now_ts: float):
        raise NotImplementedError

    @abstractmethod
    def sell(self, symbol: str, price: float, reason: str, cooldown_until: float | None = None):
        raise NotImplementedError

    @abstractmethod
    def update_trailing_stops(self):
        raise NotImplementedError
