import time
from app.config import settings
from app.utils import setup_logger
from app.market.state import MarketState
from app.market.orderbook import compute_orderbook_metrics
from app.exchange.binance_paper import BinancePaperExchange
from app.models import Portfolio
from app.storage.journal import TradeJournal
from app.risk.manager import RiskManager
from app.execution.paper_executor import PaperExecutor
from app.strategy.trend_volume_imbalance import TrendVolumeImbalanceStrategy


def bootstrap_history(exchange, market_state, logger):
    for symbol in settings.symbols:
        candles = exchange.load_initial_candles(symbol=symbol, interval="1m", limit=120)
        for c in candles:
            market_state.update_candle(symbol, c["close"], c["volume"])
        logger.info(f"Loaded {len(candles)} candles for {symbol}")


def refresh_orderbooks(exchange, market_state):
    for symbol in settings.symbols:
        raw = exchange.get_orderbook(symbol, limit=settings.orderbook_depth_levels)
        bids = [[float(p), float(q)] for p, q in raw["bids"]]
        asks = [[float(p), float(q)] for p, q in raw["asks"]]
        metrics = compute_orderbook_metrics(bids, asks, settings.orderbook_depth_levels)
        market_state.update_orderbook(symbol, metrics)
        if metrics["best_bid"] and metrics["best_ask"]:
            mid_price = (metrics["best_bid"] + metrics["best_ask"]) / 2
            market_state.last_prices[symbol] = mid_price


def refresh_latest_candle(exchange, market_state):
    for symbol in settings.symbols:
        candles = exchange.load_initial_candles(symbol=symbol, interval="1m", limit=2)
        latest = candles[-1]
        closes = market_state.get_closes(symbol)
        if not closes or closes[-1] != latest["close"]:
            market_state.update_candle(symbol, latest["close"], latest["volume"])


def recalc_equity(portfolio, market_state):
    equity = portfolio.cash
    for symbol, position in portfolio.positions.items():
        last_price = market_state.get_last_price(symbol) or position.entry_price
        equity += position.quantity * last_price
    portfolio.equity = equity


def main():
    logger = setup_logger(settings.log_level)
    logger.info("Starting crypto paper bot")

    exchange = BinancePaperExchange()
    market_state = MarketState()
    portfolio = Portfolio(cash=settings.starting_balance, equity=settings.starting_balance)
    journal = TradeJournal()
    risk_manager = RiskManager(portfolio, logger)
    executor = PaperExecutor(portfolio, journal, logger, risk_manager)
    strategy = TrendVolumeImbalanceStrategy(market_state, portfolio)

    bootstrap_history(exchange, market_state, logger)

    while True:
        try:
            refresh_latest_candle(exchange, market_state)
            refresh_orderbooks(exchange, market_state)

            for symbol in settings.symbols:
                signal = strategy.evaluate(symbol)

                if signal.action == "BUY":
                    executor.buy(symbol, signal.price, signal.reason)
                elif signal.action == "SELL":
                    executor.sell(symbol, signal.price, signal.reason)

            recalc_equity(portfolio, market_state)

            logger.info(
                f"Portfolio cash={portfolio.cash:.2f} equity={portfolio.equity:.2f} open_positions={len(portfolio.positions)}"
            )

            time.sleep(15)

        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            break
        except Exception as e:
            logger.exception(f"Main loop error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
