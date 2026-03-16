import pandas as pd


def ema(series: list[float], period: int) -> float | None:
    if len(series) < period:
        return None
    s = pd.Series(series, dtype="float64")
    return float(s.ewm(span=period, adjust=False).mean().iloc[-1])


def average(values: list[float], lookback: int) -> float | None:
    if len(values) < lookback:
        return None
    return float(sum(values[-lookback:]) / lookback)


def pct_change(old: float, new: float) -> float:
    if old == 0:
        return 0.0
    return (new - old) / old
