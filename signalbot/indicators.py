import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def add_emas(df: pd.DataFrame, periods: list[int]) -> pd.DataFrame:
    out = df.copy()
    for p in periods:
        out[f"ema{p}"] = ema(out["close"], p)
    return out


def atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    # Wilder's smoothing == EWM with alpha = 1/period
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def add_atr(df: pd.DataFrame, period: int) -> pd.DataFrame:
    out = df.copy()
    out[f"atr{period}"] = atr(out, period)
    return out


def rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    out = 100 - 100 / (1 + rs)
    # no losses at all -> rs is inf -> RSI 100 (avoid NaN from divide-by-zero)
    out = out.where(avg_loss != 0, 100.0)
    return out.astype(float)


def add_rsi(df: pd.DataFrame, period: int) -> pd.DataFrame:
    out = df.copy()
    out[f"rsi{period}"] = rsi(out["close"], period)
    return out
