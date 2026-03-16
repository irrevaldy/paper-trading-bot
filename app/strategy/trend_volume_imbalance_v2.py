from app.config import settings
from app.market.indicators import ema, average, pct_change
from app.models import Signal
from app.strategy.base import BaseStrategy


class TrendVolumeImbalanceV2Strategy(BaseStrategy):
    def __init__(self, market_state, portfolio):
        self.market_state = market_state
        self.portfolio = portfolio

    def evaluate(self, symbol: str, now_ts: float) -> Signal:
        closes = self.market_state.get_closes(symbol)
        volumes = self.market_state.get_volumes(symbol)
        orderbook = self.market_state.get_orderbook(symbol)
        price = self.market_state.get_last_price(symbol)

        if not price or not orderbook:
            return Signal(symbol, "HOLD", "waiting for market data", 0.0, 0.0)

        short_ema = ema(closes, settings.short_ema)
        long_ema = ema(closes, settings.long_ema)
        avg_volume = average(volumes, settings.volume_lookback)
        latest_volume = volumes[-1] if volumes else None

        if short_ema is None or long_ema is None or avg_volume is None or latest_volume is None:
            return Signal(symbol, "HOLD", "insufficient history", price, 0.0)

        candle_shock = False
        if len(closes) >= 2:
            move = abs(pct_change(closes[-2], closes[-1]))
            candle_shock = move >= settings.shock_move_pct

        bullish_trend = short_ema > long_ema
        bearish_trend = short_ema < long_ema
        volume_spike = latest_volume >= avg_volume * settings.volume_spike_multiplier
        healthy_spread = orderbook["spread_bps"] <= settings.max_spread_bps
        bullish_imbalance = orderbook["imbalance_ratio"] >= settings.min_imbalance_ratio
        bearish_imbalance = orderbook["imbalance_ratio"] < 0.95

        suspicious_buy_trap = orderbook["suspicious_ask_wall"] or candle_shock
        suspicious_sell_trap = orderbook["suspicious_bid_wall"] or candle_shock

        has_position = symbol in self.portfolio.positions

        if not has_position:
            if candle_shock:
                return Signal(symbol, "HOLD", "shock candle filter", price, 0.0)
            if orderbook["suspicious_ask_wall"]:
                return Signal(symbol, "HOLD", "suspicious ask wall", price, 0.0)
            if not healthy_spread:
                return Signal(symbol, "HOLD", "spread too wide", price, 0.0)

            if bullish_trend and volume_spike and bullish_imbalance:
                confidence = min(orderbook["imbalance_ratio"] / settings.min_imbalance_ratio, 2.0)
                return Signal(
                    symbol=symbol,
                    action="BUY",
                    reason="trend up + volume confirmation + bid pressure",
                    price=price,
                    confidence=confidence,
                )

            return Signal(symbol, "HOLD", "entry conditions not met", price, 0.0)

        position = self.portfolio.positions[symbol]

        if price <= position.stop_loss:
            return Signal(symbol, "SELL", "stop loss hit", price, 1.0)

        if price >= position.take_profit:
            return Signal(symbol, "SELL", "take profit hit", price, 1.0)

        if not healthy_spread and bearish_imbalance:
            return Signal(symbol, "SELL", "spread widened + sell pressure", price, 0.9)

        if bearish_trend and bearish_imbalance:
            return Signal(symbol, "SELL", "trend lost + ask pressure", price, 0.8)

        if suspicious_sell_trap and bearish_trend:
            return Signal(symbol, "SELL", "violent reversal risk", price, 0.8)

        return Signal(symbol, "HOLD", "position still valid", price, 0.0)
