import asyncio
import time

from app.config import settings
from app.exchange.indodax_ws import IndodaxWsExchange
from app.execution.indodax_live_executor import IndodaxLiveExecutor
from app.execution.paper_executor import PaperExecutor
from app.market.state import MarketState
from app.models import Portfolio, Position
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


def discover_symbols(executor, logger) -> list[str]:
    """
    Build the symbol list to watch:
    - Live mode: held assets first, then top pairs by 24h volume
    - Paper mode: top pairs by 24h volume only
    """
    logger.info("Fetching top active pairs from Indodax...")
    top_pairs = IndodaxWsExchange.fetch_active_pairs(n=settings.max_symbols)
    logger.info(f"Top {len(top_pairs)} pairs by volume: {top_pairs}")

    if settings.bot_mode != "live":
        return top_pairs

    # Add pairs where user already holds a balance
    logger.info("Fetching account balances for held asset detection...")
    balances = executor.get_all_balances()
    quote = settings.quote_asset.lower()

    held_symbols = [
        f"{asset}_{quote}"
        for asset, amount in balances.items()
        if asset != quote and amount > 0
    ]

    if held_symbols:
        logger.info(f"Held assets: {held_symbols}")

    # Merge: held symbols first (manage existing positions), then top pairs
    merged = list(dict.fromkeys(held_symbols + top_pairs))
    return merged[:settings.max_symbols]


def init_existing_positions(executor, portfolio, market_state, risk_manager, logger):
    """
    Create Position entries for crypto assets the user already holds.
    Only runs in live mode after bootstrap (so prices are available).
    """
    quote = settings.quote_asset.lower()
    balances = executor.get_all_balances()

    for asset, amount in balances.items():
        if asset == quote or amount <= 0:
            continue

        symbol = f"{asset}_{quote}"
        if symbol not in settings.symbols:
            continue
        if symbol in portfolio.positions:
            continue

        price = market_state.get_last_price(symbol)
        if not price:
            continue

        notional = amount * price
        if notional < settings.min_notional:
            continue

        stop_loss, take_profit = risk_manager.build_trade_levels(price)
        portfolio.positions[symbol] = Position(
            symbol=symbol,
            entry_price=price,
            quantity=amount,
            stop_loss=stop_loss,
            take_profit=take_profit,
            highest_price=price,
        )
        logger.info(
            f"Existing position: {symbol} qty={amount:.8f} "
            f"price={price:.0f} value={notional:.0f} IDR"
        )


async def run():
    logger = setup_logger(settings.log_level)
    logger.info("Starting Indodax trading bot")

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

    if settings.bot_mode == "live":
        executor = IndodaxLiveExecutor(portfolio, market_state, db, notifier, logger, risk_manager)
        executor.sync_balance()
        logger.info("Live mode: portfolio cash synced from Indodax account")
    else:
        executor = PaperExecutor(portfolio, market_state, db, notifier, logger, risk_manager)
        logger.info("Paper mode: using simulated portfolio")

    # Discover which symbols to trade
    settings.symbols = discover_symbols(executor, logger)
    logger.info(f"Watching {len(settings.symbols)} symbols: {settings.symbols}")

    exchange = IndodaxWsExchange()
    strategy = TrendVolumeImbalanceV3Strategy(market_state, portfolio)

    await exchange.bootstrap(market_state, logger)

    # In live mode, detect and register assets already held
    if settings.bot_mode == "live":
        init_existing_positions(executor, portfolio, market_state, risk_manager, logger)

    recalc_equity(portfolio, market_state)
    market_state.set_daily_start_equity_once(portfolio.equity)

    last_eval_ts = 0.0
    last_snapshot_ts = 0.0
    last_signal_notify: dict[str, float] = {}

    notifier.send(
        f"Indodax bot started\n"
        f"mode={settings.bot_mode}\n"
        f"symbols={len(settings.symbols)}\n"
        f"cash={portfolio.cash:.0f} {settings.quote_asset.upper()}"
    )

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
                f"Daily drawdown limit hit. equity={portfolio.equity:.0f} cash={portfolio.cash:.0f}"
            )
            return

        for symbol in settings.symbols:
            signal = strategy.evaluate(symbol, now_ts)

            if signal.action == "BUY":
                last_notify = last_signal_notify.get(symbol, 0)
                if now_ts - last_notify >= settings.cooldown_seconds:
                    notifier.send(
                        f"🟢 BUY SIGNAL\n"
                        f"Symbol : {symbol.upper()}\n"
                        f"Price  : {signal.price:,.0f} IDR\n"
                        f"Reason : {signal.reason}\n"
                        f"Confidence: {signal.confidence:.2f}"
                    )
                    last_signal_notify[symbol] = now_ts
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
                f"Portfolio cash={portfolio.cash:.0f} equity={portfolio.equity:.0f} "
                f"open_positions={len(portfolio.positions)}"
            )

            for symbol in settings.symbols:
                stats = db.fetch_symbol_stats(symbol)
                if stats["trade_count"] > 0:
                    logger.info(f"{symbol} stats: {format_symbol_stats(stats)}")

    await exchange.stream_forever(market_state, on_tick, logger)


if __name__ == "__main__":
    asyncio.run(run())
