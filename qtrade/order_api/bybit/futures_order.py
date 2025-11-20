import time
import hmac
import hashlib
import json
import urllib.parse
from typing import Any, Dict, Optional

import requests

BYBIT_BASE = "https://api.bybit.com"


class BybitFuturesClient:
    def __init__(self, api_key: str, api_secret: str, recv_window: int = 5000, timeout: int = 15):
        self.api_key = api_key
        self.api_secret = api_secret.encode()
        self.recv_window = recv_window
        self.timeout = timeout

    def _timestamp(self) -> str:
        return str(int(time.time() * 1000))

    def _headers(self, timestamp: str, signature: str) -> Dict[str, str]:
        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": str(self.recv_window),
            "Content-Type": "application/json",
        }

    def _sign(self, timestamp: str, payload: str) -> str:
        # v5: sign over (timestamp + apiKey + recvWindow + payload)
        to_sign = timestamp + self.api_key + str(self.recv_window) + payload
        return hmac.new(self.api_secret, to_sign.encode(), hashlib.sha256).hexdigest()

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None, signed: bool = False, is_get: bool = False):
        url = f"{BYBIT_BASE}{path}"
        params = dict(params or {})
        if not signed:
            if method == "GET":
                r = requests.get(url, params=params, timeout=self.timeout)
            else:
                r = requests.post(url, json=params, timeout=self.timeout)
            r.raise_for_status()
            return r.json()

        ts = self._timestamp()

        if method == "GET" or is_get:
            # Sort keys and urlencode
            query = urllib.parse.urlencode(sorted(params.items())) if params else ""
            signature = self._sign(ts, query)
            r = requests.get(url, params=params, headers=self._headers(ts, signature), timeout=self.timeout)
        else:
            # POST JSON body must be sorted keys, compact JSON
            body = json.dumps(params, separators=(",", ":"), sort_keys=True)
            signature = self._sign(ts, body)
            r = requests.post(url, data=body, headers=self._headers(ts, signature), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # -------- Public helpers --------
    def get_symbol_price(self, symbol: str) -> float:
        data = self._request("GET", "/v5/market/tickers", params={"category": "linear", "symbol": symbol}, signed=False)
        lst = (data or {}).get("result", {}).get("list", [])
        if not lst:
            raise ValueError(f"No ticker for {symbol}")
        last_price = lst[0].get("lastPrice") or lst[0].get("markPrice")
        return float(last_price)

    # -------- Orders (linear USDT perps) --------
    def place_market_order(self, symbol: str, side: str, qty: float, reduce_only: bool = False, position_idx: Optional[int] = None, client_order_id: Optional[str] = None):
        params: Dict[str, Any] = {
            "category": "linear",
            "symbol": symbol,
            "side": side.upper(),  # Buy/Sell
            "orderType": "Market",
            "qty": str(qty),
        }
        if reduce_only:
            params["reduceOnly"] = True
        if position_idx is not None:
            params["positionIdx"] = position_idx  # 0 one-way; 1 long; 2 short
        if client_order_id:
            params["orderLinkId"] = client_order_id
        return self._request("POST", "/v5/order/create", params=params, signed=True)

    def place_limit_order(self, symbol: str, side: str, qty: float, price: float, time_in_force: str = "GTC", reduce_only: bool = False, position_idx: Optional[int] = None, client_order_id: Optional[str] = None):
        params: Dict[str, Any] = {
            "category": "linear",
            "symbol": symbol,
            "side": side.upper(),
            "orderType": "Limit",
            "qty": str(qty),
            "price": f"{price:.8f}",
            "timeInForce": time_in_force,
        }
        if reduce_only:
            params["reduceOnly"] = True
        if position_idx is not None:
            params["positionIdx"] = position_idx
        if client_order_id:
            params["orderLinkId"] = client_order_id
        return self._request("POST", "/v5/order/create", params=params, signed=True)

    def cancel_order(self, symbol: str, order_id: Optional[str] = None, client_order_id: Optional[str] = None):
        params: Dict[str, Any] = {
            "category": "linear",
            "symbol": symbol,
        }
        if order_id:
            params["orderId"] = order_id
        if client_order_id:
            params["orderLinkId"] = client_order_id
        return self._request("POST", "/v5/order/cancel", params=params, signed=True)

    def cancel_all_open_orders(self, symbol: str):
        params = {
            "category": "linear",
            "symbol": symbol,
        }
        return self._request("POST", "/v5/order/cancel-all", params=params, signed=True)

    def _get_position_qty(self, symbol: str, side_hint: Optional[str] = None) -> float:
        # Fetch positions; bybit returns separate entries per side in hedge mode
        data = self._request("GET", "/v5/position/list", params={"category": "linear", "symbol": symbol}, signed=True, is_get=True)
        lst = (data or {}).get("result", {}).get("list", [])
        qty = 0.0
        side_amt = []
        for it in lst:
            side = it.get("side")  # Buy/Sell
            size = it.get("size")
            try:
                size_f = float(size) if size is not None else 0.0
            except Exception:
                size_f = 0.0
            if size_f == 0.0:
                continue
            side_amt.append((side, size_f))
        if not side_amt:
            return 0.0
        if side_hint:
            for s, a in side_amt:
                if s.lower().startswith(side_hint.lower()):
                    return a
        # default: close the largest
        return max(side_amt, key=lambda x: abs(x[1]))[1]

    def close_position_market(self, symbol: str, position_idx: Optional[int] = None):
        qty = self._get_position_qty(symbol)
        if qty == 0.0:
            return {"status": "NO_POSITION", "symbol": symbol}
        # If current net is Buy (long) then sell to close; need to know net side
        data = self._request("GET", "/v5/position/list", params={"category": "linear", "symbol": symbol}, signed=True, is_get=True)
        lst = (data or {}).get("result", {}).get("list", [])
        net_side = None
        for it in lst:
            size = float(it.get("size") or 0)
            if size != 0.0:
                net_side = it.get("side")  # Buy or Sell
                break
        side = "Sell" if (net_side == "Buy") else "Buy"
        return self.place_market_order(symbol=symbol, side=side, qty=qty, reduce_only=True, position_idx=position_idx)


def create_bybit_client(api_key: str, api_secret: str) -> BybitFuturesClient:
    return BybitFuturesClient(api_key=api_key, api_secret=api_secret)


if __name__ == "__main__":

    client = create_bybit_client(api_key="YOUR_KEY", api_secret="YOUR_SECRET")

    # Market buy 0.01 BTCUSDT
    # print(client.place_market_order(symbol="BTCUSDT", side="Buy", qty=0.01))

    # Limit sell
    # print(client.place_limit_order(symbol="BTCUSDT", side="Sell", qty=0.01, price=70000, time_in_force="GTC"))

    # Cancel order
    # print(client.cancel_order(symbol="BTCUSDT", order_id="123456"))

    # Cancel all
    # print(client.cancel_all_open_orders(symbol="BTCUSDT"))

    # Close position reduce-only market
    # print(client.close_position_market(symbol="BTCUSDT"))


