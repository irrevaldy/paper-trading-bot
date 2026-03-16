def compute_orderbook_metrics(bids: list[list[float]], asks: list[list[float]], depth: int) -> dict:
    top_bids = bids[:depth]
    top_asks = asks[:depth]

    bid_volume = sum(float(qty) for _, qty in top_bids)
    ask_volume = sum(float(qty) for _, qty in top_asks)

    best_bid = float(top_bids[0][0]) if top_bids else 0.0
    best_ask = float(top_asks[0][0]) if top_asks else 0.0

    mid = (best_bid + best_ask) / 2 if best_bid and best_ask else 0.0
    spread_bps = ((best_ask - best_bid) / mid * 10000) if mid else 999999.0
    imbalance_ratio = (bid_volume / ask_volume) if ask_volume > 0 else 999999.0

    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "bid_volume_top": bid_volume,
        "ask_volume_top": ask_volume,
        "imbalance_ratio": imbalance_ratio,
        "spread_bps": spread_bps,
    }
