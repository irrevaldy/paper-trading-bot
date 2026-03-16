from abc import ABC, abstractmethod


class BaseExchange(ABC):
    @abstractmethod
    def load_initial_candles(self, symbol: str, interval: str = "1m", limit: int = 100):
        raise NotImplementedError

    @abstractmethod
    def get_orderbook(self, symbol: str, limit: int = 10):
        raise NotImplementedError
