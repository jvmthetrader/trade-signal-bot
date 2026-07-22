import pandas as pd


def swing_high_idx(df: pd.DataFrame, strength: int) -> list[int]:
    highs = df["high"].tolist()
    n = len(highs)
    out = []
    for i in range(strength, n - strength):
        left = highs[i - strength:i]
        right = highs[i + 1:i + 1 + strength]
        if all(highs[i] > h for h in left) and all(highs[i] > h for h in right):
            out.append(i)
    return out


def swing_low_idx(df: pd.DataFrame, strength: int) -> list[int]:
    lows = df["low"].tolist()
    n = len(lows)
    out = []
    for i in range(strength, n - strength):
        left = lows[i - strength:i]
        right = lows[i + 1:i + 1 + strength]
        if all(lows[i] < l for l in left) and all(lows[i] < l for l in right):
            out.append(i)
    return out


def swing_high_values(df: pd.DataFrame, strength: int) -> list[float]:
    return [float(df["high"].iloc[i]) for i in swing_high_idx(df, strength)]


def swing_low_values(df: pd.DataFrame, strength: int) -> list[float]:
    return [float(df["low"].iloc[i]) for i in swing_low_idx(df, strength)]


def is_bullish_structure(df: pd.DataFrame, strength: int) -> bool:
    return higher_high_formed(df, strength) and higher_low_formed(df, strength)


def is_bearish_structure(df: pd.DataFrame, strength: int) -> bool:
    return lower_high_formed(df, strength) and lower_low_formed(df, strength)


def higher_high_formed(df: pd.DataFrame, strength: int) -> bool:
    v = swing_high_values(df, strength)
    return len(v) >= 2 and v[-1] > v[-2]


def lower_high_formed(df: pd.DataFrame, strength: int) -> bool:
    v = swing_high_values(df, strength)
    return len(v) >= 2 and v[-1] < v[-2]


def higher_low_formed(df: pd.DataFrame, strength: int) -> bool:
    v = swing_low_values(df, strength)
    return len(v) >= 2 and v[-1] > v[-2]


def lower_low_formed(df: pd.DataFrame, strength: int) -> bool:
    v = swing_low_values(df, strength)
    return len(v) >= 2 and v[-1] < v[-2]
