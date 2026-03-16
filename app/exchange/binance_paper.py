from binance.client import Client


class BinancePaperExchange:
    def __init__(self):
        self.client = Client()

    def load_initial_candles(self, symbol: str, interval: str = "1m", limit: int = 100):
        klines = self.client.get_klines(symbol=symbol, interval=interval, limit=limit)
        candles = []
        for k in klines:
            candles.append({
                "open_time": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": k[6],
            })
        return candles

    def get_orderbook(self, symbol: str, limit: int = 10):
        return self.client.get_order_book(symbol=symbol, limit=limit)
