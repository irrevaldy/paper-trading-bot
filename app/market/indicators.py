import pandas as pd


def ema(series: list[float], period: int) -> float | None:
    if len(series) < period:
        return None
    s = pd.Series(series, dtype="float64")
    return float(s.ewm(span=period, adjust=False).mean().iloc[-1])


def average(values: list[float], lookback: int) -> float | None:
    if len(values) < lookback:
        return None
    return sum(values[-lookback:]) / lookback
