#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX Options Client
Supports limit and market orders, order cancellation, and position management for options contracts.
"""

import os
import time
import json
import hmac
import base64
import hashlib
import requests
from typing import Optional, Dict, Any, List, Union
from decimal import Decimal
from datetime import datetime

# Import authentication credentials
from qtrade.order_api.okx import API_KEY, API_SECRET, API_PASSPHRASE


class OKXOptionsClient:
    """
    OKX Options Trading Client
    
    Features:
    - Place limit and market orders
    - Cancel orders (by ordId or clOrdId)
    - Batch cancel orders
    - Query positions and orders
    - Close positions with market orders
    - Live/Demo trading toggle
    
    Usage:
        # Live trading (default)
        client = OKXOptionsClient(simulated=False)
        
        # Demo trading
        client = OKXOptionsClient(simulated=True)
    """
    
    def __init__(self, simulated: Optional[bool] = None):
        """
        Initialize OKX Options Client
        
        Args:
            simulated: If True, use demo trading. If False, use live trading.
                      If None, read from OKX_SIMULATED env var (default: "0" = live)
        """
        self.api_key = API_KEY
        self.api_secret = API_SECRET
        self.passphrase = API_PASSPHRASE
        self.base_url = "https://www.okx.com"
        
        # Determine trading mode
        if simulated is None:
            simulated = os.getenv("OKX_SIMULATED", "0") == "1"
        
        self.simulated = simulated
        self.mode_label = "🧪 DEMO" if simulated else "🔴 LIVE"
        
        print(f"✅ OKX Options Client initialized - {self.mode_label} Trading Mode")
    
    @staticmethod
    def _get_currency_from_inst_id(inst_id: str) -> str:
        """
        Extract the settlement currency from instrument ID
        
        Args:
            inst_id: Options instrument ID (e.g., "BTC-USD-251104-100000-P")
        
        Returns:
            Currency symbol (e.g., "BTC", "ETH")
        """
        parts = inst_id.split("-")
        if len(parts) >= 1:
            return parts[0]  # BTC, ETH, etc.
        return "BTC"  # fallback
    
    def _rfc3339(self) -> str:
        """Generate RFC3339 timestamp for OKX API"""
        return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    
    def _sign(self, timestamp: str, method: str, path: str, body: str) -> str:
        """Generate HMAC-SHA256 signature for OKX API"""
        data = f"{timestamp}{method.upper()}{path}{body}"
        digest = hmac.new(
            self.api_secret.encode(),
            data.encode(),
            hashlib.sha256
        ).digest()
        return base64.b64encode(digest).decode()
    
    def _headers(self, timestamp: str, signature: str) -> Dict[str, str]:
        """Generate request headers"""
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }
        
        if self.simulated:
            headers["x-simulated-trading"] = "1"
        
        return headers
    
    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        signed: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Make HTTP request to OKX API
        
        Args:
            method: HTTP method (GET, POST)
            path: API endpoint path
            params: Query parameters (for GET)
            body: Request body (for POST)
            signed: Whether to sign the request
        
        Returns:
            API response data or None on error
        """
        timestamp = self._rfc3339()
        
        # Build URL
        url = self.base_url + path
        
        # Build request body and path for signature
        if method.upper() == "GET" and params:
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            url += f"?{query_string}"
            sign_path = f"{path}?{query_string}"
            body_str = ""
        else:
            sign_path = path
            body_str = json.dumps(body, separators=(",", ":")) if body else ""
        
        # Generate signature
        if signed:
            signature = self._sign(timestamp, method, sign_path, body_str)
            headers = self._headers(timestamp, signature)
        else:
            headers = {"Content-Type": "application/json"}
        
        # Make request
        try:
            if method.upper() == "GET":
                resp = requests.get(url, headers=headers, timeout=15)
            elif method.upper() == "POST":
                resp = requests.post(url, headers=headers, data=body_str, timeout=15)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            resp.raise_for_status()
            data = resp.json()
            
            # For trade APIs, return data even if there's an error code
            # This allows caller to handle specific error messages
            code = data.get("code")
            if code not in ("0", 0, None):
                # For public APIs, raise error
                if "/public/" in path or "/market/" in path:
                    error_msg = data.get("msg", "Unknown error")
                    raise RuntimeError(f"OKX API error {code}: {error_msg}")
                # For trade APIs, return data with error info
                else:
                    return data
            
            return data
        
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            return None
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return None
    
    # ========== Instrument Info ==========
    
    def get_instrument_info(self, inst_id: str) -> Optional[Dict[str, Any]]:
        """
        Get instrument details for an options contract
        
        Args:
            inst_id: Options instrument ID (e.g., "BTC-USD-250328-100000-C")
        
        Returns:
            Instrument info dict with lotSz, minSz, tickSz, etc.
        """
        # Extract underlying from inst_id (e.g., "BTC-USD" from "BTC-USD-251104-100000-P")
        parts = inst_id.split("-")
        if len(parts) >= 2:
            uly = f"{parts[0]}-{parts[1]}"  # e.g., "BTC-USD" or "ETH-USD"
        else:
            uly = "BTC-USD"  # fallback
        
        data = self._request(
            "GET",
            "/api/v5/public/instruments",
            params={"instType": "OPTION", "uly": uly, "instId": inst_id},
            signed=False
        )
        
        if data and data.get("data"):
            return data["data"][0]
        
        return None
    
    def get_orderbook(self, inst_id: str, depth: int = 1) -> Optional[Dict[str, Any]]:
        """
        Get orderbook for an options contract
        
        Args:
            inst_id: Options instrument ID
            depth: Orderbook depth (default: 1 for best bid/ask)
        
        Returns:
            Orderbook data with bids and asks
        """
        data = self._request(
            "GET",
            "/api/v5/market/books",
            params={"instId": inst_id, "sz": str(depth)},
            signed=False
        )
        
        if data and data.get("data"):
            book = data["data"][0]
            bids = book.get("bids", [])
            asks = book.get("asks", [])
            
            if bids and asks:
                return {
                    "inst_id": inst_id,
                    "bid": float(bids[0][0]),
                    "ask": float(asks[0][0]),
                    "mid": (float(bids[0][0]) + float(asks[0][0])) / 2,
                    "spread": float(asks[0][0]) - float(bids[0][0]),
                    "bids": bids,
                    "asks": asks,
                    "timestamp": book.get("ts")
                }
        
        return None
    
    # ========== Order Placement ==========
    
    def place_order(
        self,
        inst_id: str,
        side: str,
        sz: int,
        ord_type: str = "market",
        px: Optional[float] = None,
        cl_ord_id: Optional[str] = None,
        reduce_only: bool = False
    ) -> Dict[str, Any]:
        """
        Place an options order (market or limit)
        
        Args:
            inst_id: Options contract ID (e.g., "BTC-USD-250328-100000-C")
            side: "buy" or "sell"
            sz: Number of contracts (must be integer)
            ord_type: "market" or "limit"
            px: Price for limit orders (required if ord_type="limit")
            cl_ord_id: Client order ID (optional, for tracking)
            reduce_only: Whether this is a reduce-only order
        
        Returns:
            Order response dict
        """
        # Validate inputs
        if ord_type.lower() == "limit" and px is None:
            raise ValueError("Price (px) is required for limit orders")
        
        if not isinstance(sz, int) or sz <= 0:
            raise ValueError(f"Size must be a positive integer, got: {sz}")
        
        # Build payload
        # Note: For options, OKX requires tdMode="isolated" (not "cash" or "cross")
        payload = {
            "instId": inst_id,
            "tdMode": "isolated",  # Options must use isolated margin mode
            "side": side.lower(),
            "ordType": ord_type.lower(),
            "sz": str(sz),
        }
        
        if px is not None and ord_type.lower() == "limit":
            payload["px"] = str(px)
        
        if cl_ord_id:
            payload["clOrdId"] = cl_ord_id
        
        if reduce_only:
            payload["reduceOnly"] = "true"
        
        currency = self._get_currency_from_inst_id(inst_id)
        
        print(f"📝 [{self.mode_label}] Placing {ord_type} {side} order:")
        print(f"  🎯 Contract: {inst_id}")
        print(f"  📊 Size: {sz} contracts")
        if px:
            print(f"  💰 Price: {px:.4f} {currency}")
        
        # Place order
        data = self._request("POST", "/api/v5/trade/order", body=payload)
        
        if not data:
            return {"success": False, "error": "No response from API", "raw": None}
        
        # Check for top-level API error
        code = data.get("code")
        if code not in ("0", 0, None):
            error_msg = data.get("msg", "Unknown error")
            print(f"❌ API Error: code={code}, msg={error_msg}")
            return {
                "success": False,
                "error": f"API error {code}: {error_msg}",
                "raw": data
            }
        
        # Check order-specific response
        if data.get("data"):
            order_info = data["data"][0]
            s_code = order_info.get("sCode", "0")
            
            if s_code == "0":
                print(f"✅ Order placed successfully!")
                print(f"  🆔 Order ID: {order_info.get('ordId')}")
                return {
                    "success": True,
                    "ordId": order_info.get("ordId"),
                    "clOrdId": order_info.get("clOrdId"),
                    "sMsg": order_info.get("sMsg"),
                    "raw": data
                }
            else:
                print(f"❌ Order failed: {s_code} - {order_info.get('sMsg')}")
                return {
                    "success": False,
                    "error": f"{s_code}: {order_info.get('sMsg')}",
                    "raw": data
                }
        
        return {"success": False, "error": "No order data in response", "raw": data}
    
    def place_market_order(
        self,
        inst_id: str,
        side: str,
        sz: int,
        reduce_only: bool = False,
        cl_ord_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Place a market order for options
        
        Args:
            inst_id: Options contract ID
            side: "buy" or "sell"
            sz: Number of contracts
            reduce_only: Whether this is a reduce-only order
            cl_ord_id: Client order ID (optional)
        
        Returns:
            Order response dict
        """
        return self.place_order(
            inst_id=inst_id,
            side=side,
            sz=sz,
            ord_type="market",
            reduce_only=reduce_only,
            cl_ord_id=cl_ord_id
        )
    
    def place_limit_order(
        self,
        inst_id: str,
        side: str,
        sz: int,
        px: float,
        reduce_only: bool = False,
        cl_ord_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Place a limit order for options
        
        Args:
            inst_id: Options contract ID
            side: "buy" or "sell"
            sz: Number of contracts
            px: Limit price
            reduce_only: Whether this is a reduce-only order
            cl_ord_id: Client order ID (optional)
        
        Returns:
            Order response dict
        """
        return self.place_order(
            inst_id=inst_id,
            side=side,
            sz=sz,
            ord_type="limit",
            px=px,
            reduce_only=reduce_only,
            cl_ord_id=cl_ord_id
        )
    
    def place_limit_order_relative(
        self,
        inst_id: str,
        side: str,
        sz: int,
        offset: float = 0.0001,
        reduce_only: bool = False,
        cl_ord_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Place a limit order relative to current bid/ask
        
        Args:
            inst_id: Options contract ID
            side: "buy" or "sell"
            sz: Number of contracts
            offset: Price offset from bid (for buy) or ask (for sell)
            reduce_only: Whether this is a reduce-only order
            cl_ord_id: Client order ID (optional)
        
        Returns:
            Order response dict
        """
        # Get current orderbook
        book = self.get_orderbook(inst_id)
        if not book:
            return {
                "success": False,
                "error": "Failed to get current orderbook"
            }
        
        currency = self._get_currency_from_inst_id(inst_id)
        
        # Calculate limit price
        if side.lower() == "buy":
            limit_price = book["bid"] + offset
            print(f"💰 Current bid: {book['bid']:.4f} {currency}")
            print(f"🎯 Buy limit: {limit_price:.4f} {currency} (bid + {offset:.4f})")
        else:
            limit_price = book["ask"] - offset
            print(f"💰 Current ask: {book['ask']:.4f} {currency}")
            print(f"🎯 Sell limit: {limit_price:.4f} {currency} (ask - {offset:.4f})")
        
        return self.place_limit_order(
            inst_id=inst_id,
            side=side,
            sz=sz,
            px=limit_price,
            reduce_only=reduce_only,
            cl_ord_id=cl_ord_id
        )
    
    # ========== Contract Size Conversion ==========
    
    def _contracts_from_crypto_notional(
        self, 
        inst_id: str, 
        crypto_notional: float
    ) -> int:
        """
        Convert crypto notional (ETH/BTC amount) to contract size (sz parameter)
        
        Args:
            inst_id: Options instrument ID
            crypto_notional: Amount in base currency (e.g., 1.0 ETH)
        
        Returns:
            Number for sz parameter (integer)
        
        Note:
            OKX options use ctMult to define the actual unit of sz:
            - ctVal: face value of 1 "standard contract" (e.g., 1 ETH)
            - ctMult: multiplier for sz (e.g., 0.1 means sz=10 → 1 standard contract)
            - Actual position = sz × ctMult × ctVal
        
        Example:
            If ctVal=1 ETH, ctMult=0.1:
            - crypto_notional=1.0 ETH → sz=10 (because 10 × 0.1 × 1 = 1.0)
            - crypto_notional=1.5 ETH → sz=15 (because 15 × 0.1 × 1 = 1.5)
        """
        info = self.get_instrument_info(inst_id)
        if not info:
            raise ValueError(f"Cannot get instrument info for {inst_id}")
        
        ct_val = float(info.get("ctVal", 1))
        ct_mult = float(info.get("ctMult", 1))
        lot_sz = int(info.get("lotSz", 1))
        min_sz = int(info.get("minSz", 1))
        
        # Calculate sz: crypto_notional = sz × ctMult × ctVal
        # Therefore: sz = crypto_notional / (ctMult × ctVal)
        sz = crypto_notional / (ct_mult * ct_val)
        
        # Round to lot size
        sz_int = int(sz / lot_sz) * lot_sz
        
        if sz_int < min_sz:
            raise ValueError(
                f"Crypto notional {crypto_notional} too small: "
                f"results in sz={sz_int} (min: {min_sz})"
            )
        
        return sz_int
    
    def place_limit_order_crypto_notional(
        self,
        inst_id: str,
        side: str,
        crypto_notional: float,
        px: float,
        reduce_only: bool = False,
        cl_ord_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Place a limit order using crypto notional amount
        
        Args:
            inst_id: Options contract ID
            side: "buy" or "sell"
            crypto_notional: Amount in base currency (e.g., 1.0 ETH means 1 ETH worth of contracts)
            px: Limit price
            reduce_only: Whether this is a reduce-only order
            cl_ord_id: Client order ID (optional)
        
        Returns:
            Order response dict
        
        Example:
            # Buy 1 ETH worth of ETH options at 0.085 ETH per contract
            client.place_limit_order_crypto_notional("ETH-USD-251226-3600-P", "buy", 1.0, 0.085)
        """
        contracts = self._contracts_from_crypto_notional(inst_id, crypto_notional)
        currency = self._get_currency_from_inst_id(inst_id)
        
        print(f"💡 Converting {crypto_notional} {currency} → {contracts} contracts")
        
        return self.place_limit_order(
            inst_id=inst_id,
            side=side,
            sz=contracts,
            px=px,
            reduce_only=reduce_only,
            cl_ord_id=cl_ord_id
        )
    
    def place_market_order_crypto_notional(
        self,
        inst_id: str,
        side: str,
        crypto_notional: float,
        reduce_only: bool = False,
        cl_ord_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Place a market order using crypto notional amount
        
        Args:
            inst_id: Options contract ID
            side: "buy" or "sell"
            crypto_notional: Amount in base currency (e.g., 1.0 ETH)
            reduce_only: Whether this is a reduce-only order
            cl_ord_id: Client order ID (optional)
        
        Returns:
            Order response dict
        """
        contracts = self._contracts_from_crypto_notional(inst_id, crypto_notional)
        currency = self._get_currency_from_inst_id(inst_id)
        
        print(f"💡 Converting {crypto_notional} {currency} → {contracts} contracts")
        
        return self.place_market_order(
            inst_id=inst_id,
            side=side,
            sz=contracts,
            reduce_only=reduce_only,
            cl_ord_id=cl_ord_id
        )
    
    # ========== Helper methods for direct ordId return ==========
    
    @staticmethod
    def _ord_id_or_raise(resp: Dict[str, Any]) -> str:
        """Extract ordId from response or raise error"""
        if not resp.get("success"):
            raise RuntimeError(f"Order failed: {resp.get('error')}")
        ord_id = resp.get("ordId")
        if not ord_id:
            raise RuntimeError("No ordId in response")
        return ord_id
    
    def place_market_order_id(
        self,
        inst_id: str,
        side: str,
        sz: int,
        reduce_only: bool = False,
        cl_ord_id: Optional[str] = None
    ) -> str:
        """Place market order and return ordId directly (raises on error)"""
        resp = self.place_market_order(inst_id, side, sz, reduce_only, cl_ord_id)
        return self._ord_id_or_raise(resp)
    
    def place_limit_order_id(
        self,
        inst_id: str,
        side: str,
        sz: int,
        px: float,
        reduce_only: bool = False,
        cl_ord_id: Optional[str] = None
    ) -> str:
        """Place limit order and return ordId directly (raises on error)"""
        resp = self.place_limit_order(inst_id, side, sz, px, reduce_only, cl_ord_id)
        return self._ord_id_or_raise(resp)
    
    # ========== Order Cancellation ==========
    
    def cancel_order(
        self,
        inst_id: str,
        ord_id: Optional[str] = None,
        cl_ord_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel a single order
        
        Args:
            inst_id: Options contract ID
            ord_id: Order ID (from order response)
            cl_ord_id: Client order ID (if used when placing order)
        
        Note: Must provide either ord_id or cl_ord_id
        
        Returns:
            Cancellation response dict
        """
        if not ord_id and not cl_ord_id:
            raise ValueError("Must provide either ord_id or cl_ord_id")
        
        payload = {"instId": inst_id}
        
        if ord_id:
            payload["ordId"] = ord_id
        if cl_ord_id:
            payload["clOrdId"] = cl_ord_id
        
        print(f"🚫 [{self.mode_label}] Cancelling order:")
        print(f"  🎯 Contract: {inst_id}")
        if ord_id:
            print(f"  🆔 Order ID: {ord_id}")
        if cl_ord_id:
            print(f"  📝 Client Order ID: {cl_ord_id}")
        
        data = self._request("POST", "/api/v5/trade/cancel-order", body=payload)
        
        if data and data.get("data"):
            cancel_info = data["data"][0]
            s_code = cancel_info.get("sCode", "0")
            
            if s_code == "0":
                print(f"✅ Order cancelled successfully!")
                return {
                    "success": True,
                    "ordId": cancel_info.get("ordId"),
                    "clOrdId": cancel_info.get("clOrdId"),
                    "sMsg": cancel_info.get("sMsg"),
                    "raw": data
                }
            else:
                print(f"❌ Cancel failed: {s_code} - {cancel_info.get('sMsg')}")
                return {
                    "success": False,
                    "error": f"{s_code}: {cancel_info.get('sMsg')}",
                    "raw": data
                }
        
        return {"success": False, "error": "No response data", "raw": data}
    
    def cancel_multiple_orders(
        self,
        orders: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Cancel multiple orders in a single request
        
        Args:
            orders: List of order dicts, each with "instId" and either "ordId" or "clOrdId"
                   Example: [
                       {"instId": "BTC-USD-250328-100000-C", "ordId": "12345"},
                       {"instId": "ETH-USD-250328-5000-P", "clOrdId": "my_order_2"}
                   ]
        
        Returns:
            Batch cancellation response
        """
        if not orders or len(orders) > 20:
            raise ValueError("Must provide 1-20 orders")
        
        print(f"🚫 [{self.mode_label}] Batch cancelling {len(orders)} orders...")
        
        data = self._request("POST", "/api/v5/trade/cancel-batch-orders", body=orders)
        
        if data and data.get("data"):
            results = data["data"]
            success_count = sum(1 for r in results if r.get("sCode") == "0")
            
            print(f"✅ Successfully cancelled {success_count}/{len(results)} orders")
            
            return {
                "success": True,
                "cancelled": success_count,
                "total": len(results),
                "details": results,
                "raw": data
            }
        
        return {"success": False, "error": "No response data", "raw": data}
    
    def cancel_all_open_orders(self, inst_id: str) -> Dict[str, Any]:
        """
        Cancel all open orders for a specific options contract
        
        Args:
            inst_id: Options contract ID
        
        Returns:
            Batch cancellation result
        """
        print(f"🔍 [{self.mode_label}] Getting pending orders for {inst_id}...")
        
        # Get all pending orders
        data = self._request(
            "GET",
            "/api/v5/trade/orders-pending",
            params={"instId": inst_id},
            signed=True
        )
        
        if not data or not data.get("data"):
            print("📭 No pending orders found")
            return {
                "success": True,
                "cancelled": 0,
                "total": 0,
                "details": []
            }
        
        orders = data["data"]
        print(f"📊 Found {len(orders)} pending orders")
        
        # Build cancellation requests
        cancel_requests = []
        for order in orders:
            cancel_requests.append({
                "instId": inst_id,
                "ordId": order.get("ordId")
            })
        
        # Cancel in batches of 20 (OKX limit)
        all_results = []
        cancelled_count = 0
        
        for i in range(0, len(cancel_requests), 20):
            batch = cancel_requests[i:i+20]
            result = self.cancel_multiple_orders(batch)
            
            if result.get("success"):
                cancelled_count += result.get("cancelled", 0)
                all_results.extend(result.get("details", []))
        
        print(f"✅ Total cancelled: {cancelled_count}/{len(orders)}")
        
        return {
            "success": True,
            "cancelled": cancelled_count,
            "total": len(orders),
            "details": all_results
        }
    
    # ========== Order Query ==========
    
    def get_order_details(
        self,
        inst_id: str,
        ord_id: Optional[str] = None,
        cl_ord_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get order details
        
        Args:
            inst_id: Options contract ID
            ord_id: Order ID
            cl_ord_id: Client order ID
        
        Note: Must provide either ord_id or cl_ord_id
        
        Returns:
            Order details dict
        """
        if not ord_id and not cl_ord_id:
            raise ValueError("Must provide either ord_id or cl_ord_id")
        
        params = {"instId": inst_id}
        if ord_id:
            params["ordId"] = ord_id
        if cl_ord_id:
            params["clOrdId"] = cl_ord_id
        
        data = self._request("GET", "/api/v5/trade/order", params=params, signed=True)
        
        if data and data.get("data"):
            return data["data"][0]
        
        return None
    
    def get_pending_orders(self, inst_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all pending orders
        
        Args:
            inst_id: Options contract ID (optional, for filtering)
        
        Returns:
            List of pending orders
        """
        params = {"instType": "OPTION"}
        if inst_id:
            params["instId"] = inst_id
        
        data = self._request(
            "GET",
            "/api/v5/trade/orders-pending",
            params=params,
            signed=True
        )
        
        if data and data.get("data"):
            return data["data"]
        
        return []
    
    # ========== Position Management ==========
    
    def get_position(self, inst_id: str) -> Optional[Dict[str, Any]]:
        """
        Get position for a specific options contract
        
        Args:
            inst_id: Options contract ID
        
        Returns:
            Position dict or None if no position
        """
        data = self._request(
            "GET",
            "/api/v5/account/positions",
            params={"instType": "OPTION", "instId": inst_id},
            signed=True
        )
        
        if data and data.get("data"):
            positions = data["data"]
            for pos in positions:
                if float(pos.get("pos", 0)) != 0:
                    return pos
        
        return None
    
    def get_all_positions(self) -> List[Dict[str, Any]]:
        """
        Get all active options positions
        
        Returns:
            List of position dicts
        """
        data = self._request(
            "GET",
            "/api/v5/account/positions",
            params={"instType": "OPTION"},
            signed=True
        )
        
        if data and data.get("data"):
            # Filter for non-zero positions
            return [
                pos for pos in data["data"]
                if float(pos.get("pos", 0)) != 0
            ]
        
        return []
    
    def close_position_market(self, inst_id: str) -> Dict[str, Any]:
        """
        Close an options position using a market order
        
        Args:
            inst_id: Options contract ID
        
        Returns:
            Close order response dict
        """
        print(f"🔄 [{self.mode_label}] Closing position for {inst_id}...")
        
        # Get current position
        position = self.get_position(inst_id)
        
        if not position:
            return {
                "success": False,
                "error": f"No active position found for {inst_id}"
            }
        
        pos_size = float(position.get("pos", 0))
        
        if pos_size == 0:
            return {
                "success": False,
                "error": f"Position size is zero for {inst_id}"
            }
        
        # Determine close side and size
        if pos_size > 0:
            close_side = "sell"
            close_size = int(abs(pos_size))
            print(f"📤 Closing LONG position: {close_size} contracts")
        else:
            close_side = "buy"
            close_size = int(abs(pos_size))
            print(f"📤 Closing SHORT position: {close_size} contracts")
        
        # Place market order to close
        return self.place_market_order(
            inst_id=inst_id,
            side=close_side,
            sz=close_size,
            reduce_only=True
        )
    
    def print_position_summary(self):
        """Print a summary of all active options positions"""
        print(f"\n{'='*80}")
        print(f"📊 [{self.mode_label}] Options Position Summary")
        print(f"{'='*80}")
        
        positions = self.get_all_positions()
        
        if not positions:
            print("📭 No active options positions")
            return
        
        # Group PnL by currency
        pnl_by_currency = {}
        
        for i, pos in enumerate(positions, 1):
            inst_id = pos.get("instId", "N/A")
            pos_size = float(pos.get("pos", 0))
            avg_px = float(pos.get("avgPx", 0))
            mark_px = float(pos.get("markPx", 0))
            upl = float(pos.get("upl", 0))
            upl_ratio = float(pos.get("uplRatio", 0)) * 100
            currency = self._get_currency_from_inst_id(inst_id)
            
            side = "🟢 LONG" if pos_size > 0 else "🔴 SHORT"
            
            print(f"\n{i}. {inst_id}")
            print(f"   {side} | Size: {abs(pos_size)} contracts")
            print(f"   Avg Price: {avg_px:.4f} {currency} | Mark Price: {mark_px:.4f} {currency}")
            print(f"   Unrealized PnL: {upl:.4f} {currency} ({upl_ratio:+.2f}%)")
            
            # Accumulate PnL by currency
            if currency not in pnl_by_currency:
                pnl_by_currency[currency] = 0.0
            pnl_by_currency[currency] += upl
        
        print(f"\n{'='*80}")
        print(f"💰 Total Unrealized PnL:")
        for currency, total_upl in sorted(pnl_by_currency.items()):
            print(f"   {currency}: {total_upl:+.4f} {currency}")
        print(f"{'='*80}\n")


# ========== Main Test Script ==========

def main():
    """Test script for OKX Options Client"""
    print("🚀 OKX Options Client - Test Script\n")
    
    # Initialize client (use simulated=True for demo trading)
    # Change to simulated=False for live trading
    client = OKXOptionsClient(simulated=False)
    
    # Example options contract (BTC Put option expiring Nov 4, 2025, strike $100k)
    inst_id = "ETH-USD-251226-3600-P"
    
    print(f"\n{'='*80}")
    print(f"📊 Test Contract: {inst_id}")
    print(f"{'='*80}")
    
    # Test 1: Get instrument info
    print(f"\n🔍 Test 1: Get instrument info")
    inst_info = client.get_instrument_info(inst_id)
    if inst_info:
        print(f"✅ Instrument info retrieved:")
        print(f"  Lot Size: {inst_info.get('lotSz')}")
        print(f"  Min Size: {inst_info.get('minSz')}")
        print(f"  Tick Size: {inst_info.get('tickSz')}")
        print(f"  Contract Value: {inst_info.get('ctVal')} {inst_info.get('ctValCcy')}")
    

    # Test 2: Get orderbook
    print(f"\n📈 Test 2: Get orderbook")
    book = client.get_orderbook(inst_id)
    if book:
        print(f"✅ Orderbook retrieved:")
        print(f"  Bid: {book['bid']:.4f}")
        print(f"  Ask: {book['ask']:.4f}")
        print(f"  Mid: {book['mid']:.4f}")
        print(f"  Spread: {book['spread']:.4f}")


    
    # Test 3: Check positions
    print(f"\n📊 Test 3: Check positions")
    client.print_position_summary()


    
    # Test 4: Check pending orders
    print(f"\n📋 Test 4: Check pending orders")
    pending = client.get_pending_orders(inst_id)
    if pending:
        print(f"Found {len(pending)} pending orders:")
        for order in pending[:5]:  # Show first 5
            order_inst_id = order.get('instId', inst_id)
            currency = client._get_currency_from_inst_id(order_inst_id)
            print(f"  Order {order.get('ordId')}: {order.get('side')} {order.get('sz')} @ {order.get('px')} {currency}")
    else:
        print("No pending orders found")

    
    
    # given inst_id above, extract orderbook price and place limit order 

    orderbook = client.get_orderbook(inst_id)
    if orderbook:
        print(f"Orderbook retrieved:")
        print(f"  Bid: {orderbook['bid']:.4f}")
        print(f"  Ask: {orderbook['ask']:.4f}")
        print(f"  Mid: {orderbook['mid']:.4f}")
        print(f"  Spread: {orderbook['spread']:.4f}")
    
    tick_sz = float(inst_info.get('tickSz'))
    print(f"Tick size: {tick_sz}")
    result = client.place_limit_order_crypto_notional(inst_id = inst_id, 
                                      side = "buy", 
                                      crypto_notional = 1, 
                                      px = orderbook['bid'] - 10 * tick_sz
                                      )  
                                       
    
    if result and result.get('success'):
        ord_id = result.get('ordId')
        print(f"\n✅ Order placed successfully!")
        print(f"  Order ID: {ord_id}")
        print(f"  Price: {orderbook['bid'] - 10 * tick_sz:.4f} ETH")
        
        # Wait 30 seconds before cancelling
        print(f"\n⏳ Waiting 30 seconds before cancelling...")
        import time
        time.sleep(30)
        
        # Cancel the order
        print(f"\n🚫 Cancelling order {ord_id}...")
        cancel_result = client.cancel_order(inst_id=inst_id, ord_id=ord_id)
        
        if cancel_result.get('success'):
            print(f"✅ Order cancelled successfully!")
        else:
            print(f"❌ Cancel failed: {cancel_result.get('error')}")
            print(f"   This might mean the order was already filled or cancelled")
    else:
        print(f"❌ Order placement failed: {result.get('error') if result else 'No result'}")


if __name__ == "__main__":
    main()
