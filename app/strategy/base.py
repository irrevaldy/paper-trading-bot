from abc import ABC, abstractmethod
from app.models import Signal


class BaseStrategy(ABC):
    @abstractmethod
    def evaluate(self, symbol: str) -> Signal:
        raise NotImplementedError
