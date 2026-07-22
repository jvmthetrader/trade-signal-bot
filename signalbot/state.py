import json
import os


def load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save(path: str, state: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def already_alerted(state: dict, key: str) -> bool:
    return key in set(state.get("alerted", []))


def record(state: dict, key: str) -> None:
    alerted = state.setdefault("alerted", [])
    if key not in alerted:
        alerted.append(key)


def make_key(signal) -> str:
    lower_tf = signal.timeframes[2]
    return f"{signal.symbol}:{signal.direction}:{lower_tf}:{signal.trigger_time}"
