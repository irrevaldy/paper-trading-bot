import asyncio
import time

from app.config import settings
from app.exchange.binance_ws_v3 import BinanceWsV3Exchange
from app.execution.paper_executor import PaperExecutor
from app.market.state import MarketState
from app.models import Portfolio
from app.notify.telegram import TelegramNotifier
from app.risk.manager import RiskManager
from app.storage.db import Database
from app.storage.stats import format_symbol_stats
from app.strategy.trend_volume_imbalance_v3 import TrendVolumeImbalanceV3Strategy
from app.utils import setup_logger


def recalc_equity(portfolio, market_state):
    equity = portfolio.cash
    for symbol, position in portfolio.positions.items():
        last_price = market_state.get_last_price(symbol) or position.entry_price
        equity += position.quantity * last_price
    portfolio.equity = equity


async def run():
    logger = setup_logger(settings.log_level)
    logger.info("Starting crypto paper bot v3")

    market_state = MarketState()
    portfolio = Portfolio(cash=settings.starting_balance, equity=settings.starting_balance)
    db = Database(settings.db_path)
    notifier = TelegramNotifier(
        enabled=settings.telegram_enabled,
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        logger=logger,
    )
    risk_manager = RiskManager(portfolio, market_state, logger)
    executor = PaperExecutor(portfolio, market_state, db, notifier, logger, risk_manager)
    strategy = TrendVolumeImbalanceV3Strategy(market_state, portfolio)
    exchange = BinanceWsV3Exchange()

    await exchange.bootstrap(market_state, logger)
    recalc_equity(portfolio, market_state)
    market_state.set_daily_start_equity_once(portfolio.equity)

    last_eval_ts = 0.0
    last_snapshot_ts = 0.0

    notifier.send("Crypto paper bot v3 started")

    async def on_tick():
        nonlocal last_eval_ts
        nonlocal last_snapshot_ts

        now_ts = time.time()
        if now_ts - last_eval_ts < 1.0:
            return

        last_eval_ts = now_ts

        executor.update_trailing_stops()
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

        if now_ts - last_snapshot_ts >= 30:
            db.insert_equity_snapshot(
                cash=portfolio.cash,
                equity=portfolio.equity,
                open_positions=len(portfolio.positions),
            )
            last_snapshot_ts = now_ts

            logger.info(
                f"Portfolio cash={portfolio.cash:.2f} equity={portfolio.equity:.2f} open_positions={len(portfolio.positions)}"
            )

            for symbol in settings.symbols:
                stats = db.fetch_symbol_stats(symbol)
                logger.info(f"{symbol} stats: {format_symbol_stats(stats)}")

    await exchange.stream_forever(market_state, on_tick, logger)


if __name__ == "__main__":
    asyncio.run(run())
