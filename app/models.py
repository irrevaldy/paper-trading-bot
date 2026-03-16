from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Candle:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int


@dataclass
class OrderBookSnapshot:
    best_bid: float
    best_ask: float
    bid_volume_top: float
    ask_volume_top: float
    imbalance_ratio: float
    spread_bps: float
    ts: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Signal:
    symbol: str
    action: str  # BUY / SELL / HOLD
    reason: str
    price: float
    confidence: float = 0.0


@dataclass
class Position:
    symbol: str
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    opened_at: datetime = field(default_factory=datetime.utcnow)
    status: str = "OPEN"
    exit_price: Optional[float] = None
    closed_at: Optional[datetime] = None
    pnl: float = 0.0


@dataclass
class Portfolio:
    cash: float
    equity: float
    positions: dict[str, Position] = field(default_factory=dict)
