from app.config import settings


class RiskManager:
    def __init__(self, portfolio, market_state, logger):
        self.portfolio = portfolio
        self.market_state = market_state
        self.logger = logger

    def can_open_position(self, symbol: str, now_ts: float) -> tuple[bool, str]:
        if symbol in self.portfolio.positions:
            return False, "already in position"
        if len(self.portfolio.positions) >= settings.max_open_positions:
            return False, "max open positions reached"
        if self.market_state.in_cooldown(symbol, now_ts):
            return False, "symbol cooldown active"
        if self.daily_loss_limit_hit():
            return False, "daily drawdown limit hit"
        return True, "ok"

    def daily_loss_limit_hit(self) -> bool:
        self.market_state.set_daily_start_equity_once(self.portfolio.equity)
        start_equity = self.market_state.daily_start_equity["equity"]
        if start_equity <= 0:
            return False
        drawdown = (start_equity - self.portfolio.equity) / start_equity
        return drawdown >= settings.max_daily_drawdown_pct

    def position_size(self, price: float) -> float:
        risk_amount = self.portfolio.cash * settings.risk_per_trade
        notional = max(risk_amount, settings.min_notional)
        if price <= 0 or self.portfolio.cash <= 0:
            return 0.0
        qty = notional / price
        return qty

    def build_trade_levels(self, entry_price: float) -> tuple[float, float]:
        stop_loss = entry_price * (1 - settings.stop_loss_pct)
        take_profit = entry_price * (1 + settings.take_profit_pct)
        return stop_loss, take_profit
