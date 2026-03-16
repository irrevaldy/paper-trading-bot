import csv
import os
from datetime import datetime


class TradeJournal:
    def __init__(self, filepath: str = "logs/trades.csv"):
        self.filepath = filepath
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        if not os.path.exists(filepath):
            with open(filepath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp",
                    "symbol",
                    "action",
                    "price",
                    "quantity",
                    "reason",
                    "cash_after",
                    "realized_pnl",
                ])

    def write(self, symbol: str, action: str, price: float, quantity: float, reason: str, cash_after: float, realized_pnl: float = 0.0):
        with open(self.filepath, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.utcnow().isoformat(),
                symbol,
                action,
                round(price, 8),
                round(quantity, 8),
                reason,
                round(cash_after, 2),
                round(realized_pnl, 2),
            ])
