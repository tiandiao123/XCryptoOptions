#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX Inverse Perpetual Client (Coin-Margined Futures/Swaps)

Supports BTC-USD-SWAP, ETH-USD-SWAP, etc.
- Contract value: typically 100 USD per contract
- Margin/Settlement: BTC or ETH (coin-margined)
- Input: crypto notional (e.g., 0.001 BTC)
- Output: integer contract size

Example:
    client = OKXInversePerpClient(api_key, api_secret, passphrase)
    
    # Place market order with 0.001 BTC notional
    order_id = client.place_market_order_crypto_notional_id(
        inst_id="BTC-USD-SWAP",
        side="buy",
        crypto_notional=0.001
    )
"""

import time
import os
import json
import hmac
import base64
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List
from decimal import Decimal, ROUND_DOWN

import requests

OKX_BASE = "https://www.okx.com"
USE_SIMULATED = os.getenv("OKX_SIMULATED", "0") == "1"  # default LIVE; set 1 for demo


def _rfc3339_now_ms() -> str:
    """Generate RFC3339 timestamp with milliseconds for OKX API."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class OKXInversePerpClient:
    """
    Client for trading OKX Inverse Perpetual contracts (coin-margined).
    
    Key features:
    - Order placement using crypto notional (BTC/ETH amount)
    - Automatic conversion to USD and then to contract size
    - Support for market and limit orders
    - Order cancellation and position management
    """
    
    def __init__(self, api_key: str, api_secret: str, passphrase: str, timeout: int = 15):
        self.api_key = api_key
        self.api_secret = api_secret.encode()
        self.passphrase = passphrase
        self.timeout = timeout
        self._instrument_cache: Dict[str, Dict[str, Any]] = {}

    def _sign(self, timestamp: str, method: str, path: str, body: str) -> str:
        """Generate HMAC-SHA256 signature for OKX API."""
        payload = f"{timestamp}{method}{path}{body}"
        digest = hmac.new(self.api_secret, payload.encode(), hashlib.sha256).digest()
        return base64.b64encode(digest).decode()

    def _headers(self, timestamp: str, signature: str) -> Dict[str, str]:
        """Generate request headers with authentication."""
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
        """Generic request handler for OKX API."""
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

    # ========== Market Data ==========
    
    def get_symbol_price(self, inst_id: str) -> float:
        """Get current market price (last or mark price) for an instrument."""
        data = self._request("GET", "/api/v5/market/ticker", params={"instId": inst_id}, signed=False)
        arr = (data or {}).get("data", [])
        if not arr:
            raise ValueError(f"No ticker data for {inst_id}")
        last = arr[0].get("last") or arr[0].get("markPx")
        if not last:
            raise ValueError(f"No price available for {inst_id}")
        return float(last)

    def get_instrument_info(self, inst_id: str) -> Dict[str, Any]:
        """
        Fetch instrument specifications including ctVal, ctValCcy, lotSz, minSz.
        Results are cached to minimize API calls.
        """
        if inst_id in self._instrument_cache:
            return self._instrument_cache[inst_id]
        
        data = self._request("GET", "/api/v5/public/instruments", 
                           params={"instType": "SWAP", "instId": inst_id}, 
                           signed=False)
        arr = (data or {}).get("data", [])
        if not arr:
            raise ValueError(f"No instrument info for {inst_id}")
        
        info = arr[0]
        self._instrument_cache[inst_id] = info
        return info

    # ========== Contract Sizing ==========
    
    def _contracts_from_crypto_notional(
        self, 
        inst_id: str, 
        crypto_notional: float, 
        price: Optional[float] = None
    ) -> int:
        """
        Convert crypto notional (e.g., 0.001 BTC) to contract size for inverse perpetuals.
        
        Process:
        1. crypto_notional * current_price = USD notional
        2. USD notional / ctVal = contract count
        3. Floor to nearest integer (inverse perps typically use integer contracts)
        
        Args:
            inst_id: e.g., "BTC-USD-SWAP"
            crypto_notional: Amount in base currency (e.g., 0.001 for 0.001 BTC)
            price: Optional price; if None, fetches current market price
        
        Returns:
            Integer contract count
        
        Raises:
            ValueError: If notional is too small or instrument info unavailable
        """
        if crypto_notional <= 0:
            raise ValueError("crypto_notional must be > 0")
        
        info = self.get_instrument_info(inst_id)
        ct_val = Decimal(str(info.get("ctVal", "100")))  # typically 100 for inverse perps
        ct_val_ccy = (info.get("ctValCcy") or "").upper()
        lot_sz = Decimal(str(info.get("lotSz", "1")))  # typically 1 for inverse perps
        min_sz = Decimal(str(info.get("minSz") or str(lot_sz)))
        
        # Get current price if not provided
        if price is None:
            price = self.get_symbol_price(inst_id)
        
        # Convert crypto notional to USD notional
        usd_notional = Decimal(str(crypto_notional)) * Decimal(str(price))
        
        # Calculate contract count
        contracts = usd_notional / ct_val
        
        # Floor to lot size multiple (typically integer)
        steps = (contracts / lot_sz).to_integral_value(rounding=ROUND_DOWN)
        contracts_q = int(steps * lot_sz)
        
        if contracts_q < int(min_sz):
            raise ValueError(
                f"Crypto notional too small: {crypto_notional} {ct_val_ccy} "
                f"→ {usd_notional} USD → {contracts_q} contracts (min: {min_sz})"
            )
        
        return contracts_q

    # ========== Order Placement ==========
    
    def place_market_order(
        self,
        inst_id: str,
        side: str,
        sz: int,
        td_mode: str = "cross",
        reduce_only: bool = False,
        pos_side: Optional[str] = None,
        cl_ord_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Place a market order with explicit contract size.
        
        Args:
            inst_id: e.g., "BTC-USD-SWAP"
            side: "buy" or "sell"
            sz: Contract count (integer)
            td_mode: "cross" or "isolated"
            reduce_only: If True, only reduce existing position
            pos_side: "long" or "short" (for hedge mode)
            cl_ord_id: Client order ID
        
        Returns:
            API response dict
        """
        payload: Dict[str, Any] = {
            "instId": inst_id,
            "tdMode": td_mode,
            "side": side.lower(),
            "ordType": "market",
            "sz": str(sz),
        }
        if reduce_only:
            payload["reduceOnly"] = "true"
        if pos_side:
            payload["posSide"] = pos_side.lower()
        if cl_ord_id:
            payload["clOrdId"] = cl_ord_id
        
        return self._request("POST", "/api/v5/trade/order", params=payload, signed=True)

    def place_market_order_crypto_notional(
        self,
        inst_id: str,
        side: str,
        crypto_notional: float,
        td_mode: str = "cross",
        reduce_only: bool = False,
        pos_side: Optional[str] = None,
        cl_ord_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Place a market order sized by crypto notional (e.g., 0.001 BTC).
        
        Args:
            inst_id: e.g., "BTC-USD-SWAP"
            side: "buy" or "sell"
            crypto_notional: Amount in base currency (e.g., 0.001 for 0.001 BTC)
            td_mode: "cross" or "isolated"
            reduce_only: If True, only reduce existing position
            pos_side: "long" or "short" (for hedge mode)
            cl_ord_id: Client order ID
        
        Returns:
            API response dict with additional "conversion_info" field
        """
        price = self.get_symbol_price(inst_id)
        contracts = self._contracts_from_crypto_notional(inst_id, crypto_notional, price)
        
        resp = self.place_market_order(
            inst_id=inst_id,
            side=side,
            sz=contracts,
            td_mode=td_mode,
            reduce_only=reduce_only,
            pos_side=pos_side,
            cl_ord_id=cl_ord_id
        )
        
        # Add conversion info
        resp["conversion_info"] = {
            "crypto_notional": crypto_notional,
            "price": price,
            "usd_notional": crypto_notional * price,
            "contracts": contracts
        }
        
        return resp

    def place_limit_order(
        self,
        inst_id: str,
        side: str,
        sz: int,
        px: float,
        td_mode: str = "cross",
        time_in_force: str = "GTC",
        reduce_only: bool = False,
        pos_side: Optional[str] = None,
        cl_ord_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Place a limit order with explicit contract size and price.
        
        Args:
            inst_id: e.g., "BTC-USD-SWAP"
            side: "buy" or "sell"
            sz: Contract count (integer)
            px: Limit price
            td_mode: "cross" or "isolated"
            time_in_force: "GTC", "IOC", "FOK"
            reduce_only: If True, only reduce existing position
            pos_side: "long" or "short" (for hedge mode)
            cl_ord_id: Client order ID
        
        Returns:
            API response dict
        """
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

    def place_limit_order_crypto_notional(
        self,
        inst_id: str,
        side: str,
        crypto_notional: float,
        px: float,
        td_mode: str = "cross",
        time_in_force: str = "GTC",
        reduce_only: bool = False,
        pos_side: Optional[str] = None,
        cl_ord_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Place a limit order sized by crypto notional at specified price.
        
        Args:
            inst_id: e.g., "BTC-USD-SWAP"
            side: "buy" or "sell"
            crypto_notional: Amount in base currency (e.g., 0.001 for 0.001 BTC)
            px: Limit price
            td_mode: "cross" or "isolated"
            time_in_force: "GTC", "IOC", "FOK"
            reduce_only: If True, only reduce existing position
            pos_side: "long" or "short" (for hedge mode)
            cl_ord_id: Client order ID
        
        Returns:
            API response dict with additional "conversion_info" field
        """
        contracts = self._contracts_from_crypto_notional(inst_id, crypto_notional, px)
        
        resp = self.place_limit_order(
            inst_id=inst_id,
            side=side,
            sz=contracts,
            px=px,
            td_mode=td_mode,
            time_in_force=time_in_force,
            reduce_only=reduce_only,
            pos_side=pos_side,
            cl_ord_id=cl_ord_id
        )
        
        # Add conversion info
        resp["conversion_info"] = {
            "crypto_notional": crypto_notional,
            "price": px,
            "usd_notional": crypto_notional * px,
            "contracts": contracts
        }
        
        return resp

    # ========== Convenience: Return ordId directly ==========
    
    @staticmethod
    def _ord_id_or_raise(resp: Dict[str, Any]) -> str:
        """
        Extract ordId from API response or raise exception if order failed.
        
        Args:
            resp: API response dict
        
        Returns:
            Order ID string
        
        Raises:
            RuntimeError: If order failed or ordId not found
        """
        code = str((resp or {}).get("code"))
        if code != "0":
            data0 = ((resp or {}).get("data") or [{}])[0]
            s_code = data0.get("sCode")
            s_msg = data0.get("sMsg")
            raise RuntimeError(
                f"Order failed: code={code}, sCode={s_code}, sMsg={s_msg}"
            )
        
        data0 = ((resp or {}).get("data") or [{}])[0]
        ord_id = data0.get("ordId")
        if not ord_id:
            raise RuntimeError("Empty ordId in success response")
        
        return ord_id

    def place_market_order_id(self, *args, **kwargs) -> str:
        """Place market order and return ordId directly."""
        resp = self.place_market_order(*args, **kwargs)
        return self._ord_id_or_raise(resp)

    def place_limit_order_id(self, *args, **kwargs) -> str:
        """Place limit order and return ordId directly."""
        resp = self.place_limit_order(*args, **kwargs)
        return self._ord_id_or_raise(resp)

    def place_market_order_crypto_notional_id(self, *args, **kwargs) -> str:
        """Place market order with crypto notional and return ordId directly."""
        resp = self.place_market_order_crypto_notional(*args, **kwargs)
        return self._ord_id_or_raise(resp)

    def place_limit_order_crypto_notional_id(self, *args, **kwargs) -> str:
        """Place limit order with crypto notional and return ordId directly."""
        resp = self.place_limit_order_crypto_notional(*args, **kwargs)
        return self._ord_id_or_raise(resp)

    # ========== Order Management ==========
    
    def cancel_order(
        self,
        inst_id: str,
        ord_id: Optional[str] = None,
        cl_ord_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel an order by order ID or client order ID.
        
        Args:
            inst_id: Instrument ID
            ord_id: Order ID (from API)
            cl_ord_id: Client order ID (custom ID)
        
        Returns:
            API response dict
        """
        if not ord_id and not cl_ord_id:
            raise ValueError("Must provide either ord_id or cl_ord_id")
        
        payload: Dict[str, Any] = {"instId": inst_id}
        if ord_id:
            payload["ordId"] = ord_id
        if cl_ord_id:
            payload["clOrdId"] = cl_ord_id
        
        return self._request("POST", "/api/v5/trade/cancel-order", params=payload, signed=True)

    def cancel_all_open_orders(self, inst_id: str) -> Dict[str, Any]:
        """
        Cancel all open orders for a specific instrument.
        
        Args:
            inst_id: Instrument ID
        
        Returns:
            Dict with count of cancelled orders and details
        """
        pending = self._request(
            "GET",
            "/api/v5/trade/orders-pending",
            params={"instId": inst_id},
            signed=True
        )
        
        arr = (pending or {}).get("data", [])
        results: List[Dict[str, Any]] = []
        
        for it in arr:
            oid = it.get("ordId")
            if not oid:
                continue
            try:
                results.append(self.cancel_order(inst_id=inst_id, ord_id=oid))
            except Exception as e:
                results.append({"error": str(e), "ordId": oid})
        
        return {
            "cancelled": len(results),
            "details": results
        }

    def get_order_details(self, inst_id: str, ord_id: str) -> Optional[Dict[str, Any]]:
        """
        Get details of a specific order.
        
        Args:
            inst_id: Instrument ID
            ord_id: Order ID
        
        Returns:
            Order details dict or None if not found
        """
        data = self._request(
            "GET",
            "/api/v5/trade/order",
            params={"instId": inst_id, "ordId": ord_id},
            signed=True
        )
        
        arr = (data or {}).get("data", [])
        return arr[0] if arr else None

    # ========== Position Management ==========
    
    def get_position(
        self,
        inst_id: str,
        pos_side: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get current position for an instrument.
        
        Args:
            inst_id: Instrument ID
            pos_side: "long" or "short" (optional, for hedge mode)
        
        Returns:
            Position dict or None if no position
        """
        data = self._request(
            "GET",
            "/api/v5/account/positions",
            params={"instId": inst_id},
            signed=True
        )
        
        arr = (data or {}).get("data", [])
        for it in arr:
            if pos_side and it.get("posSide") != pos_side.lower():
                continue
            
            try:
                pos = float(it.get("pos") or 0.0)
            except Exception:
                pos = 0.0
            
            if pos != 0.0:
                return it
        
        return None

    def close_position_market(
        self,
        inst_id: str,
        pos_side: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Close an existing position using a market order.
        
        Args:
            inst_id: Instrument ID
            pos_side: "long" or "short" (optional, for hedge mode)
        
        Returns:
            API response dict or status dict if no position
        """
        pos = self.get_position(inst_id, pos_side=pos_side)
        
        if not pos:
            return {
                "status": "NO_POSITION",
                "instId": inst_id,
                "posSide": pos_side
            }
        
        try:
            size = abs(int(float(pos.get("pos") or 0.0)))
        except Exception:
            size = 0
        
        if size == 0:
            return {
                "status": "NO_POSITION",
                "instId": inst_id,
                "posSide": pos_side
            }
        
        side_now = pos.get("posSide")
        # If long, sell to close; if short, buy to close
        side = "sell" if side_now == "long" else "buy"
        
        return self.place_market_order(
            inst_id=inst_id,
            side=side,
            sz=size,
            td_mode="cross",
            reduce_only=True,
            pos_side=side_now
        )

    def get_all_positions(self) -> List[Dict[str, Any]]:
        """
        Get all open positions across all instruments.
        
        Returns:
            List of position dicts
        """
        data = self._request(
            "GET",
            "/api/v5/account/positions",
            params={},
            signed=True
        )
        
        arr = (data or {}).get("data", [])
        # Filter out zero positions
        return [it for it in arr if float(it.get("pos") or 0.0) != 0.0]


def create_okx_inverse_client(
    api_key: str,
    api_secret: str,
    passphrase: str
) -> OKXInversePerpClient:
    """
    Factory function to create OKXInversePerpClient instance.
    
    Args:
        api_key: OKX API key
        api_secret: OKX API secret
        passphrase: OKX API passphrase
    
    Returns:
        OKXInversePerpClient instance
    """
    return OKXInversePerpClient(
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase
    )


if __name__ == "__main__":
    """
    Test script for inverse perpetual client.
    """
    from qtrade.order_api.okx import API_KEY, API_SECRET, API_PASSPHRASE
    
    print("=" * 80)
    print("🚀 OKX Inverse Perpetual Client Test")
    print("=" * 80)
    
    client = create_okx_inverse_client(
        api_key=API_KEY,
        api_secret=API_SECRET,
        passphrase=API_PASSPHRASE
    )
    
    inst_id = "ETH-USD-SWAP"
    
    # Test 1: Get instrument info
    print(f"\n📋 Test 1: Get instrument info for {inst_id}")
    info = client.get_instrument_info(inst_id)
    print(f"  Contract Value: {info.get('ctVal')} {info.get('ctValCcy')}")
    print(f"  Lot Size: {info.get('lotSz')}")
    print(f"  Min Size: {info.get('minSz')}")

    
    # Test 2: Get current price
    print(f"\n💰 Test 2: Get current price")
    price = client.get_symbol_price(inst_id)
    print(f"  Current Price: ${price:,.2f}")

    
    # Test 3: Convert crypto notional to contracts
    print(f"\n🔢 Test 3: Convert crypto notional to contracts")
    crypto_notional = 0.5  # 1 ETH 
    contracts = client._contracts_from_crypto_notional(inst_id, crypto_notional, price)
    usd_notional = crypto_notional * price
    print(f"  Crypto Notional: {crypto_notional} ETH")
    print(f"  USD Notional: ${usd_notional:,.2f}")
    print(f"  Contracts: {contracts}")

    # Test 4: Get current position
    print(f"\n📊 Test 4: Get current position")
    pos = client.get_position(inst_id)
    if pos:
        print(f"  Position Side: {pos.get('posSide')}")
        print(f"  Position Size: {pos.get('pos')} contracts")
        print(f"  Avg Price: ${float(pos.get('avgPx', 0)):,.2f}")
        print(f"  Unrealized PnL: {pos.get('upl')} {pos.get('uplRatio', '0')}%")
    else:
        print(f"  No open position for {inst_id}")

    
    
    # Test 5: Check pending orders
    print(f"\n📝 Test 5: Check pending orders")
    try:
        pending = client._request(
            "GET",
            "/api/v5/trade/orders-pending",
            params={"instId": inst_id},
            signed=True
        )
        orders = (pending or {}).get("data", [])
        print(f"  Pending Orders: {len(orders)}")
        for order in orders[:3]:  # Show first 3
            print(f"    - {order.get('side')} {order.get('sz')} @ {order.get('px')} ({order.get('state')})")
    except Exception as e:
        print(f"  Error: {e}")
    
    print("\n" + "=" * 80)
    print("✅ Test complete! (No orders placed)")
    print("=" * 80)

    

    # Uncomment below to test actual order placement (BE CAREFUL - REAL MONEY!)

    print("\n⚠️  PLACING TEST ORDER (COMMENT OUT IF NOT TESTING)")
    try:
        resp = client.place_limit_order_crypto_notional(
            inst_id=inst_id,
            side="buy",
            crypto_notional=crypto_notional,  # 1 ETH
            px=3000,  # Far from market to avoid fill
            td_mode="isolated"
        )
        print(f"\n✅ Order placed successfully!")
        print(f"Response: {json.dumps(resp, indent=2)}")

        time.sleep(30)
        
        # Cancel it immediately
        ord_id = client._ord_id_or_raise(resp)
        print(f"\n🔄 Cancelling order {ord_id}...")
        cancel_resp = client.cancel_order(inst_id=inst_id, ord_id=ord_id)
        print(f"Cancel response: {json.dumps(cancel_resp, indent=2)}")
    except Exception as e:
        print(f"❌ Order test failed: {e}")
    
    