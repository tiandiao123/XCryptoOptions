import hmac
import hashlib
import time
import urllib.parse
from typing import Any, Dict, Optional

import requests

FUTURES_BASE = "https://fapi.binance.com"


class BinanceFuturesClient:
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
        url = f"{FUTURES_BASE}{path}"
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

    # Public/utility
    def get_symbol_price(self, symbol: str) -> float:
        data = self._request("GET", "/fapi/v1/ticker/price", params={"symbol": symbol}, signed=False)
        return float(data["price"]) if isinstance(data, dict) else float(data[0]["price"])  # just in case

    # Orders
    def place_market_order(self, symbol: str, side: str, quantity: float, reduce_only: bool = False, position_side: Optional[str] = None, new_client_order_id: Optional[str] = None):
        params = {
            "symbol": symbol,
            "side": side.upper(),  # BUY or SELL
            "type": "MARKET",
            "quantity": quantity,
        }
        if reduce_only:
            params["reduceOnly"] = "true"
        if position_side:
            params["positionSide"] = position_side  # LONG/SHORT (if dual position mode)
        if new_client_order_id:
            params["newClientOrderId"] = new_client_order_id
        return self._request("POST", "/fapi/v1/order", params=params, signed=True)

    def place_limit_order(self, symbol: str, side: str, quantity: float, price: float, time_in_force: str = "GTC", reduce_only: bool = False, position_side: Optional[str] = None, new_client_order_id: Optional[str] = None):
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "LIMIT",
            "timeInForce": time_in_force,
            "quantity": quantity,
            "price": f"{price:.8f}",
        }
        if reduce_only:
            params["reduceOnly"] = "true"
        if position_side:
            params["positionSide"] = position_side
        if new_client_order_id:
            params["newClientOrderId"] = new_client_order_id
        return self._request("POST", "/fapi/v1/order", params=params, signed=True)

    # Cancel orders
    def cancel_order(self, symbol: str, order_id: Optional[int] = None, orig_client_order_id: Optional[str] = None):
        params: Dict[str, Any] = {"symbol": symbol}
        if order_id is not None:
            params["orderId"] = order_id
        if orig_client_order_id is not None:
            params["origClientOrderId"] = orig_client_order_id
        return self._request("DELETE", "/fapi/v1/order", params=params, signed=True)

    def cancel_all_open_orders(self, symbol: str):
        return self._request("DELETE", "/fapi/v1/allOpenOrders", params={"symbol": symbol}, signed=True)

    # Positions
    def close_position_market(self, symbol: str, position_side: Optional[str] = None):
        # Fetch position to determine quantity to close
        positions = self._request("GET", "/fapi/v2/positionRisk", signed=True)
        qty_to_close = None
        for p in positions:
            if p.get("symbol") == symbol and (position_side is None or p.get("positionSide") == position_side):
                pos_amt = float(p.get("positionAmt", 0.0))
                if pos_amt != 0.0:
                    qty_to_close = abs(pos_amt)
                    break
        if not qty_to_close:
            return {"status": "NO_POSITION", "symbol": symbol}
        side = "SELL" if float(p.get("positionAmt", 0.0)) > 0 else "BUY"
        return self.place_market_order(symbol=symbol, side=side, quantity=qty_to_close, reduce_only=True, position_side=position_side)


# Convenience factory (expects env vars or caller to pass keys)
def create_futures_client(api_key: str, api_secret: str) -> BinanceFuturesClient:
    return BinanceFuturesClient(api_key=api_key, api_secret=api_secret)


if __name__ == "__main__":

    client = create_futures_client(api_key="YOUR_KEY", api_secret="YOUR_SECRET")

    # Market buy 0.01 BTCUSDT
    client.place_market_order(symbol="BTCUSDT", side="BUY", quantity=0.01)

    # Limit sell 0.01 at 70000, GTC
    client.place_limit_order(symbol="BTCUSDT", side="SELL", quantity=0.01, price=70000, time_in_force="GTC")

    # Cancel an order
    client.cancel_order(symbol="BTCUSDT", order_id=12345678)

    # Cancel all open orders
    client.cancel_all_open_orders(symbol="BTCUSDT")

    # Close entire position with reduce-only market
    client.close_position_market(symbol="BTCUSDT")