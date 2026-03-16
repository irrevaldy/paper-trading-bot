from abc import ABC, abstractmethod


class BaseExchange(ABC):
    @abstractmethod
    async def bootstrap(self, market_state, logger):
        raise NotImplementedError

    @abstractmethod
    async def stream_forever(self, market_state, on_tick, logger):
        raise NotImplementedError
