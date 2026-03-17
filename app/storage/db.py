import os
import sqlite3
from datetime import datetime


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        cur = self.conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL,
            price REAL NOT NULL,
            quantity REAL NOT NULL,
            reason TEXT,
            cash_after REAL NOT NULL,
            realized_pnl REAL NOT NULL
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS equity_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            cash REAL NOT NULL,
            equity REAL NOT NULL,
            open_positions INTEGER NOT NULL
        )
        """)

        self.conn.commit()

    def insert_trade(
        self,
        symbol: str,
        action: str,
        price: float,
        quantity: float,
        reason: str,
        cash_after: float,
        realized_pnl: float,
    ):
        cur = self.conn.cursor()
        cur.execute("""
        INSERT INTO trades (ts, symbol, action, price, quantity, reason, cash_after, realized_pnl)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            symbol,
            action,
            price,
            quantity,
            reason,
            cash_after,
            realized_pnl,
        ))
        self.conn.commit()

    def insert_equity_snapshot(self, cash: float, equity: float, open_positions: int):
        cur = self.conn.cursor()
        cur.execute("""
        INSERT INTO equity_snapshots (ts, cash, equity, open_positions)
        VALUES (?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            cash,
            equity,
            open_positions,
        ))
        self.conn.commit()

    def fetch_symbol_stats(self, symbol: str) -> dict:
        cur = self.conn.cursor()
        cur.execute("""
        SELECT
            COUNT(*) AS trade_count,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END), 0) AS wins,
            COALESCE(SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END), 0) AS losses
        FROM trades
        WHERE symbol = ? AND action = 'SELL'
        """, (symbol,))
        row = cur.fetchone()
        return dict(row) if row else {
            "trade_count": 0,
            "total_pnl": 0.0,
            "wins": 0,
            "losses": 0,
        }
