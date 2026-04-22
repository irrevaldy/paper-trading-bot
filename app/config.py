import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _get_list(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def _get_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    bot_mode: str = os.getenv("BOT_MODE", "paper")
    max_symbols: int = int(os.getenv("MAX_SYMBOLS", "20"))

    indodax_api_key: str = os.getenv("INDODAX_API_KEY", "")
    indodax_api_secret: str = os.getenv("INDODAX_API_SECRET", "")

    symbols: list[str] = None
    starting_balance: float = float(os.getenv("STARTING_BALANCE", "1000000"))
    quote_asset: str = os.getenv("QUOTE_ASSET", "idr")

    risk_per_trade: float = float(os.getenv("RISK_PER_TRADE", "0.01"))
    max_open_positions: int = int(os.getenv("MAX_OPEN_POSITIONS", "2"))
    stop_loss_pct: float = float(os.getenv("STOP_LOSS_PCT", "0.015"))
    take_profit_pct: float = float(os.getenv("TAKE_PROFIT_PCT", "0.03"))
    trailing_stop_pct: float = float(os.getenv("TRAILING_STOP_PCT", "0.01"))
    enable_trailing_stop: bool = _get_bool("ENABLE_TRAILING_STOP", "true")
    fee_rate: float = float(os.getenv("FEE_RATE", "0.003"))
    min_notional: float = float(os.getenv("MIN_NOTIONAL", "50000"))

    short_ema: int = int(os.getenv("SHORT_EMA", "9"))
    long_ema: int = int(os.getenv("LONG_EMA", "21"))
    volume_lookback: int = int(os.getenv("VOLUME_LOOKBACK", "20"))
    volume_spike_multiplier: float = float(os.getenv("VOLUME_SPIKE_MULTIPLIER", "1.2"))

    orderbook_depth_levels: int = int(os.getenv("ORDERBOOK_DEPTH_LEVELS", "10"))
    min_imbalance_ratio: float = float(os.getenv("MIN_IMBALANCE_RATIO", "1.15"))
    max_spread_bps: float = float(os.getenv("MAX_SPREAD_BPS", "8"))
    wall_factor: float = float(os.getenv("WALL_FACTOR", "4.0"))

    cooldown_seconds: int = int(os.getenv("COOLDOWN_SECONDS", "300"))
    shock_move_pct: float = float(os.getenv("SHOCK_MOVE_PCT", "0.015"))
    max_daily_drawdown_pct: float = float(os.getenv("MAX_DAILY_DRAWDOWN_PCT", "0.03"))

    telegram_enabled: bool = _get_bool("TELEGRAM_ENABLED", "false")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    db_path: str = os.getenv("DB_PATH", "data/trading_bot.db")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    def __post_init__(self):
        if self.symbols is None:
            self.symbols = _get_list("SYMBOLS", "btc_idr,eth_idr")


settings = Settings()
