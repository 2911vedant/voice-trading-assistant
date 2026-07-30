"""
price_feed.py
Simulated NSE-style price feed for paper trading / demo mode.
Swap `get_price()` internals for a real broker's LTP (last traded price)
call once you wire in live credentials (see broker_adapter.py).
"""

import random
import threading
import time

# Seed prices for a few well-known NSE symbols (INR).
# Extend this dict with any symbol you want to demo.
_SEED_PRICES = {
    "TATA MOTORS": 512.30,
    "TCS": 3840.00,
    "RELIANCE": 2950.50,
    "INFY": 1620.75,
    "HDFC BANK": 1710.20,
    "SBIN": 812.10,
    "WIPRO": 268.40,
}

_lock = threading.Lock()
_prices = dict(_SEED_PRICES)


def _normalize(symbol: str) -> str:
    return symbol.strip().upper()


def get_price(symbol: str) -> float:
    """Return current simulated price for a symbol. Unknown symbols get a
    plausible random seed so the demo never hard-fails on a new name."""
    symbol = _normalize(symbol)
    with _lock:
        if symbol not in _prices:
            _prices[symbol] = round(random.uniform(100, 3000), 2)
        return _prices[symbol]


def get_all_prices() -> dict:
    with _lock:
        return dict(_prices)


def _random_walk_tick():
    """Nudge every tracked price by a small random % each tick, mimicking
    real intraday jitter. Runs forever in a daemon thread."""
    while True:
        with _lock:
            for symbol in list(_prices.keys()):
                pct_move = random.uniform(-0.006, 0.006)  # +/-0.6%
                _prices[symbol] = round(_prices[symbol] * (1 + pct_move), 2)
        time.sleep(2)


def start_price_feed():
    """Call once at app startup."""
    t = threading.Thread(target=_random_walk_tick, daemon=True)
    t.start()
    return t
