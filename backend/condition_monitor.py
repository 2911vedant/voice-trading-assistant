"""
condition_monitor.py
Background watcher: every tick, checks each PENDING conditional order
against the live price feed. When the condition is satisfied, places the
order through the configured broker, logs the trade, and generates the
plain-English explanation.
"""

import threading
import time

import broker_adapter
import nlu_engine
import price_feed
import trade_log

_OPS = {
    "<": lambda price, value: price < value,
    "<=": lambda price, value: price <= value,
    ">": lambda price, value: price > value,
    ">=": lambda price, value: price >= value,
    "==": lambda price, value: price == value,
}


def _check_and_fire(broker, order: dict):
    condition = order.get("condition")
    symbol = order["asset"]
    current_price = price_feed.get_price(symbol)

    if not condition or condition.get("type") != "price":
        return None  # market orders execute immediately elsewhere, not here

    op = condition.get("operator")
    value = condition.get("value")
    check_fn = _OPS.get(op)
    if not check_fn or value is None:
        return None

    if check_fn(current_price, value):
        result = broker.place_order(
            action=order["action"],
            symbol=symbol,
            quantity=order.get("quantity") or 1,
        )
        explanation = nlu_engine.explain_execution(order, result.get("fill_price") or current_price)
        trade_entry = {**result, "explanation": explanation, "condition_id": order["id"]}
        trade_log.log_trade(trade_entry)
        trade_log.remove_condition(order["id"])
        return trade_entry
    return None


def _monitor_loop(poll_seconds: int = 3):
    broker = broker_adapter.get_broker()
    while True:
        for order in trade_log.list_active_conditions():
            try:
                _check_and_fire(broker, order)
            except Exception as e:
                # Never let one bad order kill the monitor loop.
                trade_log.log_trade({
                    "broker": getattr(broker, "name", "UNKNOWN"),
                    "status": "ERROR",
                    "condition_id": order.get("id"),
                    "explanation": f"Monitor error while evaluating condition: {e}",
                })
        time.sleep(poll_seconds)


def start_monitor():
    t = threading.Thread(target=_monitor_loop, daemon=True)
    t.start()
    return t
