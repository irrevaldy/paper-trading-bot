from datetime import datetime
from app.config import settings
from app.models import Position


class PaperExecutor:
    def __init__(self, portfolio, market_state, journal, logger, risk_manager):
        self.portfolio = portfolio
        self.market_state = market_state
        self.journal = journal
        self.logger = logger
        self.risk_manager = risk_manager

    def buy(self, symbol: str, price: float, reason: str, now_ts: float):
        can_open, why = self.risk_manager.can_open_position(symbol, now_ts)
        if not can_open:
            self.logger.info(f"SKIP BUY {symbol}: {why}")
            return

        qty = self.risk_manager.position_size(price)
        if qty <= 0:
            self.logger.warning(f"Cannot size position for {symbol}")
            return

        cost = qty * price
        fee = cost * settings.fee_rate
        total_cost = cost + fee

        if total_cost > self.portfolio.cash:
            self.logger.warning(f"Not enough cash to buy {symbol}")
            return

        stop_loss, take_profit = self.risk_manager.build_trade_levels(price)

        self.portfolio.cash -= total_cost
        self.portfolio.positions[symbol] = Position(
            symbol=symbol,
            entry_price=price,
            quantity=qty,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        self.logger.info(
            f"BUY {symbol} qty={qty:.6f} price={price:.2f} stop={stop_loss:.2f} tp={take_profit:.2f} reason={reason}"
        )
        self.journal.write(symbol, "BUY", price, qty, reason, self.portfolio.cash)

    def sell(self, symbol: str, price: float, reason: str, cooldown_until: float | None = None):
        position = self.portfolio.positions.get(symbol)
        if not position:
            return

        gross = position.quantity * price
        fee = gross * settings.fee_rate
        net = gross - fee
        entry_cost = position.quantity * position.entry_price
        pnl = net - entry_cost

        self.portfolio.cash += net
        position.exit_price = price
        position.closed_at = datetime.utcnow()
        position.status = "CLOSED"
        position.pnl = pnl

        self.logger.info(
            f"SELL {symbol} qty={position.quantity:.6f} price={price:.2f} pnl={pnl:.2f} reason={reason}"
        )
        self.journal.write(symbol, "SELL", price, position.quantity, reason, self.portfolio.cash, pnl)

        del self.portfolio.positions[symbol]

        if cooldown_until:
            self.market_state.set_cooldown(symbol, cooldown_until)
            self.logger.info(f"{symbol} cooldown active until {cooldown_until}")
