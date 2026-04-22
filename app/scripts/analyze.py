import hashlib
import hmac
import os
import time
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

load_dotenv()

from app.config import settings
from app.exchange.indodax_ws import IndodaxWsExchange
from app.market.orderbook import compute_orderbook_metrics
from app.market.state import MarketState
from app.models import Portfolio, Position
from app.risk.manager import RiskManager
from app.strategy.trend_volume_imbalance_v3 import TrendVolumeImbalanceV3Strategy

_KEY    = os.getenv("INDODAX_API_KEY", "")
_SECRET = os.getenv("INDODAX_API_SECRET", "")


# ── Indodax helpers ──────────────────────────────────────────────────────────

def _tapi(method: str) -> dict:
    nonce = int(time.time() * 1000)
    params = {"method": method, "timestamp": nonce, "nonce": nonce}
    body = urlencode(params)
    sign = hmac.new(_SECRET.encode(), body.encode(), hashlib.sha512).hexdigest()
    resp = requests.post(
        "https://indodax.com/tapi",
        data=body,
        headers={"Key": _KEY, "Sign": sign, "Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("success") != 1:
        raise RuntimeError(data.get("error", data))
    return data["return"]


def _fetch_candles(symbol: str, limit: int = 150) -> list[dict]:
    pair_id = symbol.replace("_", "").upper()
    now = int(time.time())
    resp = requests.get(
        "https://indodax.com/tradingview/history_v2",
        params={"symbol": pair_id, "tf": "1", "from": now - limit * 60, "to": now},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _fetch_orderbook(symbol: str) -> dict | None:
    pair_id = symbol.replace("_", "").lower()
    try:
        resp = requests.get(f"https://indodax.com/api/depth/{pair_id}", timeout=5)
        resp.raise_for_status()
        raw = resp.json()
        bids = [[float(p), float(q)] for p, q in raw.get("buy", [])]
        asks = [[float(p), float(q)] for p, q in raw.get("sell", [])]
        if not bids or not asks:
            return None
        return compute_orderbook_metrics(
            bids=bids, asks=asks,
            depth=settings.orderbook_depth_levels,
            wall_factor=settings.wall_factor,
        )
    except Exception:
        return None


def _fetch_price(symbol: str) -> float | None:
    pair_id = symbol.replace("_", "").lower()
    try:
        resp = requests.get(f"https://indodax.com/api/ticker/{pair_id}", timeout=5)
        resp.raise_for_status()
        return float(resp.json()["ticker"]["last"])
    except Exception:
        return None


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    quote = settings.quote_asset.lower()

    # 1. Fetch balances
    print("Fetching account balances...")
    balance      = {}
    balance_hold = {}
    if _KEY and _SECRET:
        try:
            raw          = _tapi("getInfo")
            balance      = {k: float(v) for k, v in raw.get("balance", {}).items()      if float(v) > 0}
            balance_hold = {k: float(v) for k, v in raw.get("balance_hold", {}).items() if float(v) > 0}
        except Exception as e:
            print(f"  Warning: {e}")

    # All crypto assets held (free + in open orders), exclude quote
    held_assets = {
        asset: balance.get(asset, 0) + balance_hold.get(asset, 0)
        for asset in set(balance) | set(balance_hold)
        if asset != quote
    }
    held_assets = {k: v for k, v in held_assets.items() if v > 0}

    held_symbols = [f"{asset}_{quote}" for asset in held_assets]

    # 2. Discover top market symbols
    print("Fetching top active pairs...")
    top_pairs = IndodaxWsExchange.fetch_active_pairs(n=settings.max_symbols)

    # Held symbols always included; fill remaining slots with top pairs
    extra = [s for s in top_pairs if s not in held_symbols]
    symbols = held_symbols + extra
    symbols = symbols[:settings.max_symbols]

    print(f"Analyzing {len(symbols)} symbols ({len(held_symbols)} held)...\n")

    # 3. Build market state
    market_state = MarketState()
    portfolio    = Portfolio(cash=balance.get(quote, 0), equity=0)
    risk_manager = RiskManager(portfolio, market_state, None)

    # Register held positions (no min_notional filter — show everything)
    for asset, qty in held_assets.items():
        symbol = f"{asset}_{quote}"
        price  = _fetch_price(symbol)
        if not price:
            continue
        sl, tp = risk_manager.build_trade_levels(price)
        portfolio.positions[symbol] = Position(
            symbol=symbol,
            entry_price=price,
            quantity=qty,
            stop_loss=sl,
            take_profit=tp,
            highest_price=price,
        )

    strategy = TrendVolumeImbalanceV3Strategy(market_state, portfolio)

    # 4. Feed candles + orderbook for every symbol
    for symbol in symbols:
        try:
            candles = _fetch_candles(symbol)
            for c in candles:
                market_state.update_candle(symbol, float(c["Close"]), float(c["Volume"]))
        except Exception:
            pass

        ob = _fetch_orderbook(symbol)
        if ob:
            market_state.update_orderbook(symbol, ob)

        price = _fetch_price(symbol) or market_state.get_last_price(symbol)
        if price:
            market_state.last_prices[symbol] = price

    # 5. Evaluate signals
    now_ts  = time.time()
    results = []
    for symbol in symbols:
        signal   = strategy.evaluate(symbol, now_ts)
        position = portfolio.positions.get(symbol)
        price    = market_state.get_last_price(symbol)

        value_idr      = None
        unrealized_pct = None
        if position and price:
            value_idr      = position.quantity * price
            unrealized_pct = (price - position.entry_price) / position.entry_price * 100

        results.append({
            "symbol":          symbol,
            "signal":          signal.action,
            "reason":          signal.reason,
            "price":           price,
            "confidence":      signal.confidence,
            "held":            symbol in portfolio.positions,
            "qty":             held_assets.get(symbol.split("_")[0], 0),
            "value_idr":       value_idr,
            "unrealized_pct":  unrealized_pct,
        })

    # ── Print: held currencies first ─────────────────────────────────────────
    held_results = [r for r in results if r["held"]]
    buy_results  = [r for r in results if r["signal"] == "BUY"  and not r["held"]]
    hold_results = [r for r in results if r["signal"] == "HOLD" and not r["held"]]

    SIGNAL_LABEL = {"BUY": "🟢 BUY", "SELL": "🔴 SELL", "HOLD": "⚪ HOLD"}

    def fmt_price(p):
        return f"{p:,.0f}" if p else "n/a"

    def fmt_idr(v):
        return f"{v:,.0f}" if v else "─"

    # ── Section 1: Your holdings ──────────────────────────────────────────────
    print("=" * 80)
    print("  YOUR HOLDINGS — BUY / SELL RECOMMENDATION")
    print("=" * 80)

    if not held_results:
        print("  No crypto holdings detected.\n")
    else:
        print(f"  {'SYMBOL':<14} {'QTY':>16} {'PRICE (IDR)':>18} {'VALUE (IDR)':>14} {'SIGNAL':<10} REASON")
        print("  " + "─" * 78)
        for r in held_results:
            signal_lbl = SIGNAL_LABEL[r["signal"]]
            pnl_str    = f"  PnL {r['unrealized_pct']:+.2f}%" if r["unrealized_pct"] is not None else ""
            print(
                f"  {r['symbol'].upper():<14} {r['qty']:>16.6f} "
                f"{fmt_price(r['price']):>18} {fmt_idr(r['value_idr']):>14} "
                f"{signal_lbl:<10} {r['reason']}{pnl_str}"
            )
        print()

    # ── Section 2: Buy opportunities ──────────────────────────────────────────
    print("=" * 80)
    print("  BUY OPPORTUNITIES (not yet holding)")
    print("=" * 80)

    actual_buys = [r for r in buy_results]
    if not actual_buys:
        print("  No buy signals right now.\n")
    else:
        print(f"  {'SYMBOL':<14} {'PRICE (IDR)':>18} {'CONFIDENCE':>12}  REASON")
        print("  " + "─" * 60)
        for r in sorted(actual_buys, key=lambda x: x["confidence"], reverse=True):
            print(
                f"  {r['symbol'].upper():<14} {fmt_price(r['price']):>18} "
                f"{r['confidence']:>12.2f}  {r['reason']}"
            )
        print()

    # ── Section 3: Hold summary ───────────────────────────────────────────────
    print("=" * 80)
    print("  HOLD (not yet entering)")
    print("=" * 80)
    print(f"  {'SYMBOL':<14} {'PRICE (IDR)':>18}  REASON")
    print("  " + "─" * 60)
    for r in hold_results:
        print(f"  {r['symbol'].upper():<14} {fmt_price(r['price']):>18}  {r['reason']}")
    print()

    # ── Footer ────────────────────────────────────────────────────────────────
    total_held_idr = sum(r["value_idr"] for r in held_results if r["value_idr"])
    idr_cash       = balance.get(quote, 0)
    print(f"  IDR cash available : {idr_cash:>18,.0f} IDR")
    print(f"  Crypto holdings    : {total_held_idr:>18,.0f} IDR")
    print(f"  Total portfolio    : {idr_cash + total_held_idr:>18,.0f} IDR")
    print()


if __name__ == "__main__":
    main()
