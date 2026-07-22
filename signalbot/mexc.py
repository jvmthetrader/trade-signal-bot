import requests
import pandas as pd

from signalbot.config import TF_TO_INTERVAL

BASE_URL = "https://contract.mexc.com/api/v1/contract/kline"


def to_interval(timeframe: str) -> str:
    if timeframe not in TF_TO_INTERVAL:
        raise ValueError(f"unsupported timeframe: {timeframe!r}")
    return TF_TO_INTERVAL[timeframe]


def parse_klines(payload: dict) -> pd.DataFrame:
    if not payload or not payload.get("success", False):
        raise ValueError(f"MEXC returned unsuccessful payload: {payload!r}")
    data = payload.get("data") or {}
    times = data.get("time") or []
    if not times:
        raise ValueError("MEXC payload contained no candles")
    df = pd.DataFrame(
        {
            "time": data["time"],
            "open": data["open"],
            "high": data["high"],
            "low": data["low"],
            "close": data["close"],
            "volume": data.get("vol", [0] * len(times)),
        }
    )
    return df.astype(
        {"open": float, "high": float, "low": float, "close": float, "volume": float}
    )


def get_klines(symbol: str, timeframe: str, limit: int = 400) -> pd.DataFrame:
    interval = to_interval(timeframe)
    url = f"{BASE_URL}/{symbol}"
    resp = requests.get(url, params={"interval": interval}, timeout=15)
    resp.raise_for_status()
    df = parse_klines(resp.json())
    if len(df) > limit:
        df = df.iloc[-limit:].reset_index(drop=True)
    return df
