from abc import ABC, abstractmethod
from app.models import Signal


class BaseStrategy(ABC):
    @abstractmethod
    def evaluate(self, symbol: str, now_ts: float) -> Signal:
        raise NotImplementedError
