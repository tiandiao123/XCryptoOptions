import time
import json
import hmac
import base64
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple, List

import requests

OKX_BASE = "https://www.okx.com"


def _rfc3339_now_ms() -> str:
    # e.g. 2023-06-30T12:30:00.123Z
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class OKXFuturesClient:
    def __init__(self, api_key: str, api_secret: str, passphrase: str, timeout: int = 15):
        self.api_key = api_key
        self.api_secret = api_secret.encode()
        self.passphrase = passphrase
        self.timeout = timeout

    def _sign(self, timestamp: str, method: str, path: str, body: str) -> str:
        # sign content = timestamp + method + requestPath + body
        payload = f"{timestamp}{method}{path}{body}"
        digest = hmac.new(self.api_secret, payload.encode(), hashlib.sha256).digest()
        return base64.b64encode(digest).decode()

    def _headers(self, timestamp: str, signature: str) -> Dict[str, str]:
        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None, signed: bool = False):
        url = f"{OKX_BASE}{path}"
        method_up = method.upper()
        if not signed:
            if method_up == "GET":
                r = requests.get(url, params=params, timeout=self.timeout)
            else:
                r = requests.post(url, json=params or {}, timeout=self.timeout)
            r.raise_for_status()
            return r.json()

        ts = _rfc3339_now_ms()
        if method_up == "GET":
            # include querystring in path for signature
            qs = ""
            if params:
                qs = "?" + requests.compat.urlencode(params)
            sign_path = f"{path}{qs}"
            sign_body = ""
            sig = self._sign(ts, method_up, sign_path, sign_body)
            r = requests.get(url, params=params, headers=self._headers(ts, sig), timeout=self.timeout)
        else:
            body = json.dumps(params or {}, separators=(",", ":"))
            sig = self._sign(ts, method_up, path, body)
            r = requests.post(url, data=body, headers=self._headers(ts, sig), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # ---------- Market data helpers ----------
    def get_symbol_price(self, inst_id: str) -> float:
        data = self._request("GET", "/api/v5/market/ticker", params={"instId": inst_id}, signed=False)
        arr = (data or {}).get("data", [])
        if not arr:
            raise ValueError(f"No ticker for {inst_id}")
        last = arr[0].get("last") or arr[0].get("markPx")
        return float(last)

    # ---------- Trading (USDT-M SWAP) ----------
    def place_market_order(self, inst_id: str, side: str, sz: str, td_mode: str = "cross", reduce_only: bool = False, pos_side: Optional[str] = None, cl_ord_id: Optional[str] = None):
        payload: Dict[str, Any] = {
            "instId": inst_id,
            "tdMode": td_mode,            # cross / isolated
            "side": side.lower(),         # buy / sell
            "ordType": "market",
            "sz": str(sz),
        }
        if reduce_only:
            payload["reduceOnly"] = "true"
        if pos_side:
            payload["posSide"] = pos_side.lower()  # long / short
        if cl_ord_id:
            payload["clOrdId"] = cl_ord_id
        return self._request("POST", "/api/v5/trade/order", params=payload, signed=True)

    def place_limit_order(self, inst_id: str, side: str, sz: str, px: float, td_mode: str = "cross", time_in_force: str = "GTC", reduce_only: bool = False, pos_side: Optional[str] = None, cl_ord_id: Optional[str] = None):
        payload: Dict[str, Any] = {
            "instId": inst_id,
            "tdMode": td_mode,
            "side": side.lower(),
            "ordType": "limit",
            "sz": str(sz),
            "px": f"{px:.8f}",
            "timeInForce": time_in_force,
        }
        if reduce_only:
            payload["reduceOnly"] = "true"
        if pos_side:
            payload["posSide"] = pos_side.lower()
        if cl_ord_id:
            payload["clOrdId"] = cl_ord_id
        return self._request("POST", "/api/v5/trade/order", params=payload, signed=True)

    def cancel_order(self, inst_id: str, ord_id: Optional[str] = None, cl_ord_id: Optional[str] = None):
        payload: Dict[str, Any] = {"instId": inst_id}
        if ord_id:
            payload["ordId"] = ord_id
        if cl_ord_id:
            payload["clOrdId"] = cl_ord_id
        return self._request("POST", "/api/v5/trade/cancel-order", params=payload, signed=True)

    def cancel_all_open_orders(self, inst_id: str):
        # Simple approach: query pending orders then cancel by batch (loop)
        pending = self._request("GET", "/api/v5/trade/orders-pending", params={"instId": inst_id}, signed=True)
        arr = (pending or {}).get("data", [])
        results: List[Dict[str, Any]] = []
        for it in arr:
            oid = it.get("ordId")
            if not oid:
                continue
            results.append(self.cancel_order(inst_id=inst_id, ord_id=oid))
        return {"cancelled": len(results), "details": results}

    # ---------- Positions ----------
    def _get_position(self, inst_id: str, pos_side: Optional[str] = None) -> Optional[Dict[str, Any]]:
        data = self._request("GET", "/api/v5/account/positions", params={"instId": inst_id}, signed=True)
        arr = (data or {}).get("data", [])
        for it in arr:
            if pos_side and it.get("posSide") != pos_side.lower():
                continue
            # return first non-zero position
            try:
                pos = float(it.get("pos") or 0.0)
            except Exception:
                pos = 0.0
            if pos != 0.0:
                return it
        return None

    def close_position_market(self, inst_id: str, pos_side: Optional[str] = None):
        pos = self._get_position(inst_id, pos_side=pos_side)
        if not pos:
            return {"status": "NO_POSITION", "instId": inst_id}
        try:
            size = abs(float(pos.get("pos") or 0.0))
        except Exception:
            size = 0.0
        if size == 0.0:
            return {"status": "NO_POSITION", "instId": inst_id}
        side_now = pos.get("posSide")
        # If long, sell to close; if short, buy to close
        side = "sell" if side_now == "long" else "buy"
        return self.place_market_order(inst_id=inst_id, side=side, sz=str(int(size)), td_mode="cross", reduce_only=True, pos_side=side_now)


def create_okx_client(api_key: str, api_secret: str, passphrase: str) -> OKXFuturesClient:
    return OKXFuturesClient(api_key=api_key, api_secret=api_secret, passphrase=passphrase)


if __name__ == "__main__":

    client = create_okx_client(api_key="YOUR_KEY", api_secret="YOUR_SECRET", passphrase="YOUR_PASSPHRASE")

    # Market buy 1 contract BTC-USDT-SWAP (size is contract qty)
    # print(client.place_market_order(inst_id="BTC-USDT-SWAP", side="buy", sz="1"))

    # Limit sell
    # print(client.place_limit_order(inst_id="BTC-USDT-SWAP", side="sell", sz="1", px=70000))

    # Cancel
    # print(client.cancel_order(inst_id="BTC-USDT-SWAP", ord_id="123456789"))

    # Cancel all pending
    # print(client.cancel_all_open_orders(inst_id="BTC-USDT-SWAP"))

    # Close position
    # print(client.close_position_market(inst_id="BTC-USDT-SWAP"))


