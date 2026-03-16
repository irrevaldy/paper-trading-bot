import asyncio
import time

from app.config import settings
from app.exchange.binance_ws import BinanceWsExchange
from app.execution.paper_executor import PaperExecutor
from app.market.state import MarketState
from app.models import Portfolio
from app.risk.manager import RiskManager
from app.storage.journal import TradeJournal
from app.strategy.trend_volume_imbalance_v2 import TrendVolumeImbalanceV2Strategy
from app.utils import setup_logger


def recalc_equity(portfolio, market_state):
    equity = portfolio.cash
    for symbol, position in portfolio.positions.items():
        last_price = market_state.get_last_price(symbol) or position.entry_price
        equity += position.quantity * last_price
    portfolio.equity = equity


async def run():
    logger = setup_logger(settings.log_level)
    logger.info("Starting crypto paper bot v2")

    market_state = MarketState()
    portfolio = Portfolio(cash=settings.starting_balance, equity=settings.starting_balance)
    journal = TradeJournal()
    risk_manager = RiskManager(portfolio, market_state, logger)
    executor = PaperExecutor(portfolio, market_state, journal, logger, risk_manager)
    strategy = TrendVolumeImbalanceV2Strategy(market_state, portfolio)
    exchange = BinanceWsExchange()

    await exchange.bootstrap(market_state, logger)
    recalc_equity(portfolio, market_state)
    market_state.set_daily_start_equity_once(portfolio.equity)

    last_eval_ts = 0.0

    async def on_tick():
        nonlocal last_eval_ts

        now_ts = time.time()
        if now_ts - last_eval_ts < 1.0:
            return

        last_eval_ts = now_ts

        recalc_equity(portfolio, market_state)
        market_state.reset_day_if_needed(portfolio.equity)

        if risk_manager.daily_loss_limit_hit():
            logger.warning(
                f"Daily drawdown limit hit. equity={portfolio.equity:.2f} cash={portfolio.cash:.2f}"
            )
            return

        for symbol in settings.symbols:
            signal = strategy.evaluate(symbol, now_ts)

            if signal.action == "BUY":
                executor.buy(symbol, signal.price, signal.reason, now_ts)

            elif signal.action == "SELL":
                cooldown_until = now_ts + settings.cooldown_seconds
                executor.sell(symbol, signal.price, signal.reason, cooldown_until)

        recalc_equity(portfolio, market_state)
        logger.info(
            f"Portfolio cash={portfolio.cash:.2f} equity={portfolio.equity:.2f} open_positions={len(portfolio.positions)}"
        )

    await exchange.stream_forever(market_state, on_tick, logger)


if __name__ == "__main__":
    asyncio.run(run())
