import hashlib
import hmac
import time
from datetime import datetime
from urllib.parse import urlencode

import requests

from app.config import settings
from app.execution.base import BaseExecutor
from app.models import Position


class IndodaxLiveExecutor(BaseExecutor):
    TAPI_URL = "https://indodax.com/tapi"

    def __init__(self, portfolio, market_state, db, notifier, logger, risk_manager):
        if not settings.indodax_api_key or not settings.indodax_api_secret:
            raise RuntimeError("INDODAX_API_KEY and INDODAX_API_SECRET must be set for live mode")

        self.portfolio = portfolio
        self.market_state = market_state
        self.db = db
        self.notifier = notifier
        self.logger = logger
        self.risk_manager = risk_manager
        self._nonce = int(time.time() * 1000)

    # ─────────────────────────────────────────────
    # Auth helpers
    # ─────────────────────────────────────────────

    def _get_nonce(self) -> int:
        self._nonce += 1
        return self._nonce

    def _sign(self, body: str) -> str:
        return hmac.new(
            settings.indodax_api_secret.encode(),
            body.encode(),
            hashlib.sha512,
        ).hexdigest()

    def _request(self, method: str, params: dict) -> dict:
        params["method"] = method
        params["timestamp"] = int(time.time() * 1000)
        params["nonce"] = self._get_nonce()

        body = urlencode(params)
        headers = {
            "Key": settings.indodax_api_key,
            "Sign": self._sign(body),
            "Content-Type": "application/x-www-form-urlencoded",
        }

        resp = requests.post(self.TAPI_URL, data=body, headers=headers, timeout=10)
        resp.raise_for_status()

        data = resp.json()
        if data.get("success") != 1:
            raise RuntimeError(f"Indodax API error: {data.get('error', data)}")

        return data["return"]

    # ─────────────────────────────────────────────
    # Balance sync
    # ─────────────────────────────────────────────

    def sync_balance(self):
        result = self._request("getInfo", {})
        balance = result.get("balance", {})
        quote = settings.quote_asset.lower()
        self.portfolio.cash = float(balance.get(quote, 0))
        self.logger.info(f"Balance synced: {quote.upper()}={self.portfolio.cash:.2f}")

    def get_all_balances(self) -> dict[str, float]:
        """Returns all non-zero asset balances."""
        result = self._request("getInfo", {})
        return {
            asset: float(amount)
            for asset, amount in result.get("balance", {}).items()
            if float(amount) > 0
        }

    # ─────────────────────────────────────────────
    # Order placement
    # ─────────────────────────────────────────────

    def _place_buy(self, symbol: str, idr_amount: float) -> dict:
        return self._request("trade", {
            "pair": symbol,
            "type": "buy",
            "order_type": "market",
            settings.quote_asset.lower(): int(idr_amount),
        })

    def _place_sell(self, symbol: str, quantity: float) -> dict:
        base = symbol.split("_")[0].lower()
        return self._request("trade", {
            "pair": symbol,
            "type": "sell",
            "order_type": "market",
            base: quantity,
        })

    # ─────────────────────────────────────────────
    # BaseExecutor interface
    # ─────────────────────────────────────────────

    def buy(self, symbol: str, price: float, reason: str, now_ts: float):
        can_open, why = self.risk_manager.can_open_position(symbol, now_ts)
        if not can_open:
            self.logger.info(f"SKIP BUY {symbol}: {why}")
            return

        qty = self.risk_manager.position_size(price)
        if qty <= 0:
            self.logger.warning(f"Cannot size position for {symbol}")
            return

        notional = qty * price

        try:
            result = self._place_buy(symbol, notional)
        except Exception as e:
            self.logger.error(f"BUY order failed for {symbol}: {e}")
            return

        base = symbol.split("_")[0].lower()
        fill_qty = float(result.get(f"receive_{base}", 0))
        spend = float(result.get(f"spend_{settings.quote_asset.lower()}", notional))
        fill_price = spend / fill_qty if fill_qty > 0 else price

        if fill_qty <= 0:
            self.logger.warning(f"BUY {symbol} returned zero fill qty")
            return

        stop_loss, take_profit = self.risk_manager.build_trade_levels(fill_price)

        self.portfolio.positions[symbol] = Position(
            symbol=symbol,
            entry_price=fill_price,
            quantity=fill_qty,
            stop_loss=stop_loss,
            take_profit=take_profit,
            highest_price=fill_price,
        )

        self.sync_balance()

        self.logger.info(
            f"BUY {symbol} qty={fill_qty:.8f} price={fill_price:.2f} "
            f"stop={stop_loss:.2f} tp={take_profit:.2f} reason={reason}"
        )
        self.db.insert_trade(symbol, "BUY", fill_price, fill_qty, reason, self.portfolio.cash, 0.0)
        self.notifier.send(
            f"BUY {symbol}\nprice={fill_price:.2f}\nqty={fill_qty:.8f}"
            f"\nreason={reason}\ncash={self.portfolio.cash:.2f}"
        )

    def sell(self, symbol: str, price: float, reason: str, cooldown_until: float | None = None):
        position = self.portfolio.positions.get(symbol)
        if not position:
            return

        try:
            result = self._place_sell(symbol, position.quantity)
        except Exception as e:
            self.logger.error(f"SELL order failed for {symbol}: {e}")
            return

        quote = settings.quote_asset.lower()
        base = symbol.split("_")[0].lower()
        received = float(result.get(f"receive_{quote}", 0))
        fill_qty = float(result.get(f"spend_{base}", position.quantity))
        fill_price = received / fill_qty if fill_qty > 0 else price

        entry_cost = position.quantity * position.entry_price
        fee = received * settings.fee_rate
        net = received - fee
        pnl = net - entry_cost

        position.exit_price = fill_price
        position.closed_at = datetime.utcnow()
        position.status = "CLOSED"
        position.pnl = pnl

        del self.portfolio.positions[symbol]
        self.sync_balance()

        self.logger.info(
            f"SELL {symbol} qty={fill_qty:.8f} price={fill_price:.2f} pnl={pnl:.2f} reason={reason}"
        )
        self.db.insert_trade(symbol, "SELL", fill_price, fill_qty, reason, self.portfolio.cash, pnl)
        self.notifier.send(
            f"SELL {symbol}\nprice={fill_price:.2f}\nqty={fill_qty:.8f}"
            f"\npnl={pnl:.2f}\nreason={reason}\ncash={self.portfolio.cash:.2f}"
        )

        if cooldown_until:
            self.market_state.set_cooldown(symbol, cooldown_until)
            self.logger.info(f"{symbol} cooldown active until {cooldown_until}")

    def update_trailing_stops(self):
        if not settings.enable_trailing_stop:
            return

        for symbol, position in self.portfolio.positions.items():
            last_price = self.market_state.get_last_price(symbol)
            if not last_price:
                continue

            if last_price > position.highest_price:
                position.highest_price = last_price

            trailing_stop_candidate = position.highest_price * (1 - settings.trailing_stop_pct)
            if trailing_stop_candidate > position.stop_loss:
                position.stop_loss = trailing_stop_candidate
