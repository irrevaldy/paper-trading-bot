from app.config import settings


class RiskManager:
    def __init__(self, portfolio, logger):
        self.portfolio = portfolio
        self.logger = logger

    def can_open_position(self, symbol: str) -> bool:
        if symbol in self.portfolio.positions:
            return False
        if len(self.portfolio.positions) >= settings.max_open_positions:
            return False
        return True

    def position_size(self, price: float) -> float:
        risk_amount = self.portfolio.cash * settings.risk_per_trade
        if risk_amount <= 0 or price <= 0:
            return 0.0
        qty = risk_amount / price
        return qty

    def build_trade_levels(self, entry_price: float) -> tuple[float, float]:
        stop_loss = entry_price * (1 - settings.stop_loss_pct)
        take_profit = entry_price * (1 + settings.take_profit_pct)
        return stop_loss, take_profit
