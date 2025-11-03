import time
import os
import json
import hmac
import base64
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple, List

import requests
from decimal import Decimal, ROUND_DOWN

OKX_BASE = "https://www.okx.com"
USE_SIMULATED = os.getenv("OKX_SIMULATED", "0") == "1"  # default LIVE; set 1 for demo


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
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }
        if USE_SIMULATED:
            headers["x-simulated-trading"] = "1"
        return headers

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

    def get_instrument_info(self, inst_id: str) -> Dict[str, Any]:
        """Fetch instrument meta including ctVal, ctValCcy, lotSz, minSz."""
        data = self._request("GET", "/api/v5/public/instruments", params={"instType": "SWAP", "instId": inst_id}, signed=False)
        arr = (data or {}).get("data", [])
        return arr[0] if arr else {}

    def _contracts_from_usdt(self, inst_id: str, notional_usdt: float, price: Optional[float] = None) -> str:
        """Convert USDT notional to contract size respecting lot/min size.

        Uses Decimal precision and floors to the nearest lot size; raises if below minSz.
        Returns a string suitable for API `sz` (can be fractional, e.g., 0.01).
        """
        if notional_usdt <= 0:
            raise ValueError("notional_usdt must be > 0")
        info = self.get_instrument_info(inst_id)
        if not info:
            raise ValueError(f"No instrument info for {inst_id}")

        ct_val = Decimal(str(info.get("ctVal") or "0"))
        ct_ccy = (info.get("ctValCcy") or "").upper()
        lot_sz = Decimal(str(info.get("lotSz") or "1"))
        min_sz = Decimal(str(info.get("minSz") or str(lot_sz)))

        if ct_ccy == "USDT":
            contracts = Decimal(str(notional_usdt)) / ct_val
        else:
            if price is None:
                price = self.get_symbol_price(inst_id)
            contracts = Decimal(str(notional_usdt)) / (Decimal(str(price)) * ct_val)
        
        print(f"contracts: {contracts}")
        print(f"ct_val: {ct_val}, ct_ccy: {ct_ccy}, lot_sz: {lot_sz}, min_sz: {min_sz}")
        print(f"notional_usdt: {notional_usdt}, price: {price}")

        # floor to lot multiple
        steps = (contracts / lot_sz).to_integral_value(rounding=ROUND_DOWN)
        contracts_q = steps * lot_sz

        print(f"contracts_q: {contracts_q}")

        if contracts_q < min_sz:
            raise ValueError("Notional too small to satisfy minSz for this instrument")

        # format with the same precision as lot size
        precision = max(0, -lot_sz.as_tuple().exponent)
        return f"{contracts_q:.{precision}f}"

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

    def place_market_order_usdt(self, 
                            inst_id: str, 
                            side: str, 
                            notional_usdt: float, 
                            td_mode: str = "cross", 
                            reduce_only: bool = False, 
                            pos_side: Optional[str] = None, 
                            cl_ord_id: Optional[str] = None
                            ):
        """Place a market order sized by USDT notional.

        Computes contract size from notional using ctVal and current price.
        """
        contracts = self._contracts_from_usdt(inst_id=inst_id, notional_usdt=notional_usdt)
        return self.place_market_order(inst_id=inst_id, side=side, sz=contracts, td_mode=td_mode, reduce_only=reduce_only, pos_side=pos_side, cl_ord_id=cl_ord_id)

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

    def place_limit_order_usdt(self, inst_id: str, side: str, notional_usdt: float, px: float, td_mode: str = "cross", time_in_force: str = "GTC", reduce_only: bool = False, pos_side: Optional[str] = None, cl_ord_id: Optional[str] = None):
        """Place a limit order sized by USDT notional at price px."""
        contracts = self._contracts_from_usdt(inst_id=inst_id, notional_usdt=notional_usdt, price=px)
        return self.place_limit_order(inst_id=inst_id, side=side, sz=contracts, px=px, td_mode=td_mode, time_in_force=time_in_force, reduce_only=reduce_only, pos_side=pos_side, cl_ord_id=cl_ord_id)

    # ---------- Convenience: return ordId directly ----------
    @staticmethod
    def _ord_id_or_raise(resp: Dict[str, Any]) -> str:
        code = str((resp or {}).get("code"))
        if code != "0":
            data0 = ((resp or {}).get("data") or [{}])[0]
            s_code = data0.get("sCode")
            s_msg = data0.get("sMsg")
            raise RuntimeError(f"Order failed: code={code}, sCode={s_code}, sMsg={s_msg}")
        data0 = ((resp or {}).get("data") or [{}])[0]
        ord_id = data0.get("ordId")
        if not ord_id:
            raise RuntimeError("Empty ordId in success response")
        return ord_id

    def place_market_order_id(self, *args, **kwargs) -> str:
        resp = self.place_market_order(*args, **kwargs)
        return self._ord_id_or_raise(resp)

    def place_limit_order_id(self, *args, **kwargs) -> str:
        resp = self.place_limit_order(*args, **kwargs)
        return self._ord_id_or_raise(resp)

    def place_market_order_usdt_id(self, *args, **kwargs) -> str:
        resp = self.place_market_order_usdt(*args, **kwargs)
        return self._ord_id_or_raise(resp)

    def place_limit_order_usdt_id(self, *args, **kwargs) -> str:
        resp = self.place_limit_order_usdt(*args, **kwargs)
        return self._ord_id_or_raise(resp)

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
    from qtrade.order_api.okx import API_KEY, API_SECRET, API_PASSPHRASE

    client = create_okx_client(api_key=API_KEY, api_secret=API_SECRET, passphrase=API_PASSPHRASE)

    # Market buy 1 contract BTC-USDT-SWAP (size is contract qty)
    # print(client.place_market_order(inst_id="BTC-USDT-SWAP", side="buy", sz="1"))

    # Limit buy 

    resp = client.place_limit_order_usdt(inst_id="BTC-USDT-SWAP", side="buy", notional_usdt=300, px=70000, td_mode="isolated")


    ord_id = OKXFuturesClient._ord_id_or_raise(resp)
    print(f"Order placed with ID: {ord_id}")

    


