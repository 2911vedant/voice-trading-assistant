"""
broker_adapter.py
Pluggable broker interface. PaperBroker is the default and is what runs
unless you explicitly switch BROKER_MODE and supply real credentials.

--------------------------------------------------------------------------
IMPORTANT / HONEST NOTES BEFORE YOU WIRE UP REAL MONEY:

Zerodha (Kite Connect):
  - Kite Connect is a paid API product (subscription billed separately
    from your trading account). You must register an app at
    https://developers.kite.trade, get an api_key/api_secret, and complete
    the daily login/token-exchange flow (a browser redirect + request_token
    -> access_token exchange) — this cannot be fully automated headlessly
    because of the login step. ZerodhaBroker below assumes you've already
    obtained a valid access_token for the day and stored it in .env.
  - Install: pip install kiteconnect

Groww:
  - Groww has been rolling out an API product for algo/programmatic
    trading, separate from their retail app. Since this is newer than
    what I can fully verify, GrowwBroker below is a STUB with the
    interface shape only — check Groww's current official API docs for
    exact auth flow, package name, and method signatures before using it,
    and update the TODOs. Do not assume the method names here are final.

Both real adapters place LIVE orders if actually called. Nothing in this
codebase calls them automatically — the condition monitor and the /confirm
endpoint always route through whatever broker is selected in config, and
PaperBroker is the safe default.
--------------------------------------------------------------------------
"""

import os
import uuid
from abc import ABC, abstractmethod
from datetime import datetime

import price_feed


class BrokerAdapter(ABC):
    @abstractmethod
    def place_order(self, action: str, symbol: str, quantity: int, order_type: str = "MARKET") -> dict:
        ...

    @abstractmethod
    def get_ltp(self, symbol: str) -> float:
        ...


class PaperBroker(BrokerAdapter):
    """Default, safe. Simulates fills against price_feed, no real money,
    no external API calls."""

    name = "PAPER"

    def get_ltp(self, symbol: str) -> float:
        return price_feed.get_price(symbol)

    def place_order(self, action: str, symbol: str, quantity: int, order_type: str = "MARKET") -> dict:
        fill_price = self.get_ltp(symbol)
        order_id = f"PAPER-{uuid.uuid4().hex[:10].upper()}"
        return {
            "broker": self.name,
            "order_id": order_id,
            "status": "FILLED",
            "action": action,
            "symbol": symbol,
            "quantity": quantity,
            "fill_price": fill_price,
            "order_type": order_type,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }


class ZerodhaBroker(BrokerAdapter):
    """
    Real Kite Connect adapter. Requires:
      pip install kiteconnect
      env vars: KITE_API_KEY, KITE_ACCESS_TOKEN
    access_token must be refreshed daily via Kite's login flow — see
    https://kite.trade/docs/connect/v3/user/#login-flow
    """

    name = "ZERODHA"

    def __init__(self):
        try:
            from kiteconnect import KiteConnect
        except ImportError as e:
            raise RuntimeError(
                "kiteconnect not installed. Run: pip install kiteconnect"
            ) from e

        api_key = os.environ.get("KITE_API_KEY")
        access_token = os.environ.get("KITE_ACCESS_TOKEN")
        if not api_key or not access_token:
            raise RuntimeError(
                "KITE_API_KEY / KITE_ACCESS_TOKEN missing. Complete the Kite "
                "login flow and set them before using ZerodhaBroker."
            )

        self.kite = KiteConnect(api_key=api_key)
        self.kite.set_access_token(access_token)

    def get_ltp(self, symbol: str) -> float:
        # Kite expects "EXCHANGE:TRADINGSYMBOL", e.g. "NSE:TATAMOTORS".
        instrument = f"NSE:{symbol.replace(' ', '')}"
        quote = self.kite.ltp([instrument])
        return quote[instrument]["last_price"]

    def place_order(self, action: str, symbol: str, quantity: int, order_type: str = "MARKET") -> dict:
        tradingsymbol = symbol.replace(" ", "")
        transaction_type = self.kite.TRANSACTION_TYPE_BUY if action == "BUY" else self.kite.TRANSACTION_TYPE_SELL

        order_id = self.kite.place_order(
            variety=self.kite.VARIETY_REGULAR,
            exchange=self.kite.EXCHANGE_NSE,
            tradingsymbol=tradingsymbol,
            transaction_type=transaction_type,
            quantity=quantity,
            order_type=self.kite.ORDER_TYPE_MARKET,
            product=self.kite.PRODUCT_CNC,
        )
        return {
            "broker": self.name,
            "order_id": order_id,
            "status": "SUBMITTED",  # Kite orders are async; poll order status separately
            "action": action,
            "symbol": symbol,
            "quantity": quantity,
            "fill_price": None,
            "order_type": order_type,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }


class GrowwBroker(BrokerAdapter):
    """
    STUB. Fill this in against Groww's current official API documentation
    before use — auth flow, SDK package name, and method signatures below
    are placeholders, not verified against a live spec.
    """

    name = "GROWW"

    def __init__(self):
        raise NotImplementedError(
            "GrowwBroker is a stub. Check Groww's current API docs "
            "(developer/algo-trading API) and implement auth + order "
            "placement here before use."
        )

    def get_ltp(self, symbol: str) -> float:
        raise NotImplementedError

    def place_order(self, action: str, symbol: str, quantity: int, order_type: str = "MARKET") -> dict:
        raise NotImplementedError


def get_broker() -> BrokerAdapter:
    """
    Selects broker based on BROKER_MODE env var. Defaults to PAPER so the
    system is safe out of the box. Set BROKER_MODE=ZERODHA or GROWW only
    once you've supplied real, valid credentials.
    """
    mode = os.environ.get("BROKER_MODE", "PAPER").upper()
    if mode == "ZERODHA":
        return ZerodhaBroker()
    if mode == "GROWW":
        return GrowwBroker()
    return PaperBroker()
