import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _get_list(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [x.strip().upper() for x in raw.split(",") if x.strip()]


@dataclass
class Settings:
    bot_mode: str = os.getenv("BOT_MODE", "paper")
    symbols: list[str] = None
    quote_asset: str = os.getenv("QUOTE_ASSET", "USDT")
    starting_balance: float = float(os.getenv("STARTING_BALANCE", "10000"))
    risk_per_trade: float = float(os.getenv("RISK_PER_TRADE", "0.01"))
    max_open_positions: int = int(os.getenv("MAX_OPEN_POSITIONS", "2"))
    stop_loss_pct: float = float(os.getenv("STOP_LOSS_PCT", "0.015"))
    take_profit_pct: float = float(os.getenv("TAKE_PROFIT_PCT", "0.03"))
    fee_rate: float = float(os.getenv("FEE_RATE", "0.001"))
    short_ema: int = int(os.getenv("SHORT_EMA", "9"))
    long_ema: int = int(os.getenv("LONG_EMA", "21"))
    volume_lookback: int = int(os.getenv("VOLUME_LOOKBACK", "20"))
    volume_spike_multiplier: float = float(os.getenv("VOLUME_SPIKE_MULTIPLIER", "1.2"))
    orderbook_depth_levels: int = int(os.getenv("ORDERBOOK_DEPTH_LEVELS", "10"))
    min_imbalance_ratio: float = float(os.getenv("MIN_IMBALANCE_RATIO", "1.15"))
    max_spread_bps: float = float(os.getenv("MAX_SPREAD_BPS", "8"))
    cooldown_seconds: int = int(os.getenv("COOLDOWN_SECONDS", "300"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    def __post_init__(self):
        if self.symbols is None:
            self.symbols = _get_list("SYMBOLS", "BTCUSDT,ETHUSDT")


settings = Settings()
