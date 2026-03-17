from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Signal:
    symbol: str
    action: str
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
    highest_price: float
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
