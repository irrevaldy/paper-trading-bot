class LocalOrderBook:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.bids = {}
        self.asks = {}
        self.last_update_id = None
        self.buffer = []
        self.snapshot_loaded = False

    def load_snapshot(self, snapshot: dict):
        self.last_update_id = snapshot["lastUpdateId"]
        self.bids = {float(price): float(qty) for price, qty in snapshot.get("bids", []) if float(qty) > 0}
        self.asks = {float(price): float(qty) for price, qty in snapshot.get("asks", []) if float(qty) > 0}
        self.snapshot_loaded = True

    def buffer_event(self, event: dict):
        self.buffer.append(event)

    def apply_buffered_events(self):
        remaining = []
        for event in self.buffer:
            if self._event_relevant(event):
                self.apply_event(event)
            else:
                remaining.append(event)
        self.buffer = remaining

    def _event_relevant(self, event: dict) -> bool:
        if self.last_update_id is None:
            return False
        first_id = event["U"]
        final_id = event["u"]
        return final_id >= self.last_update_id + 1

    def apply_event(self, event: dict):
        first_id = event["U"]
        final_id = event["u"]

        if self.last_update_id is not None and final_id <= self.last_update_id:
            return

        if self.last_update_id is not None and first_id > self.last_update_id + 1:
            raise RuntimeError(f"{self.symbol} order book gap detected")

        for price, qty in event.get("b", []):
            self._update_side(self.bids, float(price), float(qty))

        for price, qty in event.get("a", []):
            self._update_side(self.asks, float(price), float(qty))

        self.last_update_id = final_id

    def _update_side(self, side: dict, price: float, qty: float):
        if qty == 0:
            side.pop(price, None)
        else:
            side[price] = qty

    def top_n_bids(self, n: int) -> list[list[float]]:
        return [[price, qty] for price, qty in sorted(self.bids.items(), key=lambda x: x[0], reverse=True)[:n]]

    def top_n_asks(self, n: int) -> list[list[float]]:
        return [[price, qty] for price, qty in sorted(self.asks.items(), key=lambda x: x[0])[:n]]
