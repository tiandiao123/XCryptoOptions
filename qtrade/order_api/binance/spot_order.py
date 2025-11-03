import hmac
import hashlib
import time
import urllib.parse
from typing import Any, Dict, Optional

import requests

SPOT_BASE = "https://api.binance.com"


class BinanceSpotClient:
    def __init__(self, api_key: str, api_secret: str, recv_window: int = 5000, timeout: int = 15):
        self.api_key = api_key
        self.api_secret = api_secret.encode()
        self.recv_window = recv_window
        self.timeout = timeout

    def _sign(self, query: str) -> str:
        return hmac.new(self.api_secret, query.encode(), hashlib.sha256).hexdigest()

    def _headers(self) -> Dict[str, str]:
        return {"X-MBX-APIKEY": self.api_key}

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None, signed: bool = False):
        url = f"{SPOT_BASE}{path}"
        params = dict(params or {})
        if signed:
            params.setdefault("timestamp", int(time.time() * 1000))
            params.setdefault("recvWindow", self.recv_window)
            query = urllib.parse.urlencode(params, doseq=True)
            params["signature"] = self._sign(query)
        if method.upper() == "GET":
            r = requests.get(url, headers=self._headers() if signed else None, params=params, timeout=self.timeout)
        elif method.upper() == "POST":
            r = requests.post(url, headers=self._headers() if signed else None, params=params, timeout=self.timeout)
        elif method.upper() == "DELETE":
            r = requests.delete(url, headers=self._headers() if signed else None, params=params, timeout=self.timeout)
        else:
            raise ValueError(f"Unsupported method: {method}")
        r.raise_for_status()
        return r.json()

    # Public
    def get_symbol_price(self, symbol: str) -> float:
        data = self._request("GET", "/api/v3/ticker/price", params={"symbol": symbol}, signed=False)
        return float(data["price"]) if isinstance(data, dict) else float(data[0]["price"])  # just in case

    # Orders
    def place_market_order(self, symbol: str, side: str, quantity: Optional[float] = None, quote_order_qty: Optional[float] = None, new_client_order_id: Optional[str] = None):
        params: Dict[str, Any] = {
            "symbol": symbol,
            "side": side.upper(),  # BUY or SELL
            "type": "MARKET",
        }
        if quantity is not None:
            params["quantity"] = quantity
        if quote_order_qty is not None:
            params["quoteOrderQty"] = quote_order_qty
        if new_client_order_id:
            params["newClientOrderId"] = new_client_order_id
        return self._request("POST", "/api/v3/order", params=params, signed=True)

    def place_limit_order(self, symbol: str, side: str, quantity: float, price: float, time_in_force: str = "GTC", new_client_order_id: Optional[str] = None):
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "LIMIT",
            "timeInForce": time_in_force,
            "quantity": quantity,
            "price": f"{price:.8f}",
        }
        if new_client_order_id:
            params["newClientOrderId"] = new_client_order_id
        return self._request("POST", "/api/v3/order", params=params, signed=True)

    # Cancel orders
    def cancel_order(self, symbol: str, order_id: Optional[int] = None, orig_client_order_id: Optional[str] = None):
        params: Dict[str, Any] = {"symbol": symbol}
        if order_id is not None:
            params["orderId"] = order_id
        if orig_client_order_id is not None:
            params["origClientOrderId"] = orig_client_order_id
        return self._request("DELETE", "/api/v3/order", params=params, signed=True)

    def cancel_all_open_orders(self, symbol: str):
        return self._request("DELETE", "/api/v3/openOrders", params={"symbol": symbol}, signed=True)


def create_spot_client(api_key: str, api_secret: str) -> BinanceSpotClient:
    return BinanceSpotClient(api_key=api_key, api_secret=api_secret)


if __name__ == "__main__":

    client = create_spot_client(api_key="YOUR_KEY", api_secret="YOUR_SECRET")

    # Market buy 100 USDT worth of BTC
    client.place_market_order(symbol="BTCUSDT", side="BUY", quote_order_qty=100)

    # Market sell 0.01 BTC
    client.place_market_order(symbol="BTCUSDT", side="SELL", quantity=0.01)

    # Limit buy 0.01 at 60000
    client.place_limit_order(symbol="BTCUSDT", side="BUY", quantity=0.01, price=60000, time_in_force="GTC")

    # Cancel a specific order
    client.cancel_order(symbol="BTCUSDT", order_id=12345678)

    # Cancel all open orders
    client.cancel_all_open_orders(symbol="BTCUSDT")


