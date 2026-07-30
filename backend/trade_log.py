"""
trade_log.py
Simple in-memory store for active conditional orders and executed trade
history. Swap for SQLite/Postgres if you want persistence across restarts.
"""

import itertools
import threading
from datetime import datetime

_lock = threading.Lock()
_id_counter = itertools.count(1)

active_conditions = {}   # id -> order dict, status "PENDING"
trade_history = []       # list of executed trade dicts (most recent last)


def add_condition(order: dict) -> int:
    with _lock:
        cid = next(_id_counter)
        order = dict(order)
        order["id"] = cid
        order["status"] = "PENDING"
        order["created_at"] = datetime.utcnow().isoformat() + "Z"
        active_conditions[cid] = order
        return cid


def remove_condition(cid: int):
    with _lock:
        active_conditions.pop(cid, None)


def list_active_conditions() -> list:
    with _lock:
        return list(active_conditions.values())


def log_trade(entry: dict):
    with _lock:
        entry = dict(entry)
        entry["logged_at"] = datetime.utcnow().isoformat() + "Z"
        trade_history.append(entry)


def list_trade_history() -> list:
    with _lock:
        return list(reversed(trade_history))  # newest first
