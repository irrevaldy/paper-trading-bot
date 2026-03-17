def format_symbol_stats(stats: dict) -> str:
    trade_count = stats.get("trade_count", 0)
    total_pnl = stats.get("total_pnl", 0.0)
    wins = stats.get("wins", 0)
    losses = stats.get("losses", 0)

    win_rate = (wins / trade_count * 100) if trade_count > 0 else 0.0

    return (
        f"trades={trade_count} "
        f"wins={wins} "
        f"losses={losses} "
        f"win_rate={win_rate:.1f}% "
        f"total_pnl={total_pnl:.2f}"
    )
