def compute_orderbook_metrics(
    bids: list[list[float]],
    asks: list[list[float]],
    depth: int,
    wall_factor: float,
) -> dict:
    top_bids = bids[:depth]
    top_asks = asks[:depth]

    bid_volume = sum(float(qty) for _, qty in top_bids)
    ask_volume = sum(float(qty) for _, qty in top_asks)

    best_bid = float(top_bids[0][0]) if top_bids else 0.0
    best_ask = float(top_asks[0][0]) if top_asks else 0.0

    mid = (best_bid + best_ask) / 2 if best_bid and best_ask else 0.0
    spread_bps = ((best_ask - best_bid) / mid * 10000) if mid else 999999.0
    imbalance_ratio = (bid_volume / ask_volume) if ask_volume > 0 else 999999.0

    max_bid_qty = max((float(q) for _, q in top_bids), default=0.0)
    max_ask_qty = max((float(q) for _, q in top_asks), default=0.0)

    avg_bid_qty = bid_volume / len(top_bids) if top_bids else 0.0
    avg_ask_qty = ask_volume / len(top_asks) if top_asks else 0.0

    suspicious_bid_wall = avg_bid_qty > 0 and max_bid_qty >= avg_bid_qty * wall_factor
    suspicious_ask_wall = avg_ask_qty > 0 and max_ask_qty >= avg_ask_qty * wall_factor

    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "bid_volume_top": bid_volume,
        "ask_volume_top": ask_volume,
        "imbalance_ratio": imbalance_ratio,
        "spread_bps": spread_bps,
        "max_bid_qty": max_bid_qty,
        "max_ask_qty": max_ask_qty,
        "avg_bid_qty": avg_bid_qty,
        "avg_ask_qty": avg_ask_qty,
        "suspicious_bid_wall": suspicious_bid_wall,
        "suspicious_ask_wall": suspicious_ask_wall,
    }
