#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX Options Order Placement Module
Support placing limit and market orders for BTC/ETH options contracts
"""

import os, time, json, hmac, base64, hashlib, requests
from typing import Optional, Dict, Any, Union, List
from datetime import datetime

# Import authentication from __init__.py
from qtrade.demo_trade.order_placer import API_KEY, API_SECRET, API_PASSPHRASE

OKX_BASE_URL = "https://www.okx.com"
SIM_HEADER = {"x-simulated-trading": "1"}  # Demo trading header


def rfc3339():
    """Generate RFC3339 timestamp"""
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())


def sign(timestamp: str, method: str, path: str, body: str, secret: str) -> str:
    """Generate OKX API signature"""
    data = f"{timestamp}{method.upper()}{path}{body}"
    digest = hmac.new(secret.encode(), data.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def auth_headers(ts: str, sig: str) -> Dict[str, str]:
    """Generate authentication headers"""
    return {
        "OK-ACCESS-KEY": API_KEY,
        "OK-ACCESS-SIGN": sig,
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": API_PASSPHRASE,
        "Content-Type": "application/json",
        **SIM_HEADER,
    }


def okx_post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Make authenticated POST request to OKX API"""
    ts = rfc3339()
    body = json.dumps(payload, separators=(",", ":"))
    sig = sign(ts, "POST", path, body, API_SECRET)
    
    resp = requests.post(
        OKX_BASE_URL + path,
        headers=auth_headers(ts, sig),
        data=body,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    
    if data.get("code") not in ("0", 0, None):
        raise RuntimeError(f"OKX error {data.get('code')}: {data.get('msg')} | data={data}")
    
    return data


def okx_get(path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Make authenticated GET request to OKX API"""
    ts = rfc3339()
    query_string = ""
    if params:
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        path_with_query = f"{path}?{query_string}"
    else:
        path_with_query = path
    
    sig = sign(ts, "GET", path_with_query, "", API_SECRET)
    
    url = OKX_BASE_URL + path
    if query_string:
        url += f"?{query_string}"
    
    resp = requests.get(
        url,
        headers=auth_headers(ts, sig),
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    
    if data.get("code") not in ("0", 0, None):
        raise RuntimeError(f"OKX error {data.get('code')}: {data.get('msg')} | data={data}")
    
    return data


def get_options_bid_ask(instId: str) -> Optional[Dict[str, Any]]:
    """
    Get current bid/ask prices for an options contract
    
    Args:
        instId: Options contract ID, e.g., "BTC-USD-241227-100000-C"
    
    Returns:
        Dict: Bid/ask price information
    """
    try:
        url = f"{OKX_BASE_URL}/api/v5/market/books?instId={instId}&sz=1"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("code") == "0" and data.get("data"):
            book = data["data"][0]
            
            bids = book.get("bids", [])
            asks = book.get("asks", [])
            
            if bids and asks:
                bid_price = float(bids[0][0])
                ask_price = float(asks[0][0])
                
                return {
                    "instId": instId,
                    "bid": bid_price,
                    "ask": ask_price,
                    "mid_price": (bid_price + ask_price) / 2,
                    "spread": ask_price - bid_price,
                    "timestamp": book.get("ts", "")
                }
        
        return None
        
    except Exception as e:
        print(f"⚠️ Error getting bid/ask for {instId}: {e}")
        return None


def place_options_order(
    instId: str,
    side: str,  # "buy" or "sell"
    sz: int,    # Number of contracts (integer)
    ordType: str = "market",  # "market" or "limit"
    px: Optional[float] = None,  # Price for limit orders
    tdMode: str = "cash",  # Trading mode: "cash" for options
    clOrdId: Optional[str] = None,  # Client order ID
    reduceOnly: bool = False,  # Reduce-only flag
    tgtCcy: str = ""  # Target currency (empty for options)
) -> Dict[str, Any]:
    """
    Place an options order (market or limit)
    
    Args:
        instId: Options contract ID, e.g., "BTC-USD-241227-100000-C"
        side: "buy" or "sell"
        sz: Number of contracts (must be integer)
        ordType: "market" or "limit"
        px: Price for limit orders (required for limit orders)
        tdMode: Trading mode, "cash" for options
        clOrdId: Client order ID (optional)
        reduceOnly: Whether this is a reduce-only order
        tgtCcy: Target currency (empty for options)
    
    Returns:
        Dict: Order result with order ID and status
    """
    print(f"📝 Placing {ordType} {side} order for {instId}...")
    
    # Validate inputs
    if ordType.lower() == "limit" and px is None:
        raise ValueError("Price (px) is required for limit orders")
    
    if not isinstance(sz, int) or sz <= 0:
        raise ValueError("Size (sz) must be a positive integer")
    
    # Build payload
    payload = {
        "instId": instId,
        "tdMode": tdMode,
        "side": side.lower(),
        "ordType": ordType.lower(),
        "sz": str(sz),
    }
    
    # Add price for limit orders
    if px is not None and ordType.lower() == "limit":
        payload["px"] = str(px)
    
    # Add optional parameters
    if clOrdId:
        payload["clOrdId"] = clOrdId
    
    if reduceOnly:
        payload["reduceOnly"] = "true"
    
    if tgtCcy:
        payload["tgtCcy"] = tgtCcy
    
    print(f"📊 Order details:")
    print(f"  🎯 Contract: {instId}")
    print(f"  📈 Side: {side.upper()}")
    print(f"  📊 Size: {sz} contracts")
    print(f"  🎯 Type: {ordType.upper()}")
    if px:
        print(f"  💰 Price: ${px:.4f}")
    
    try:
        result = okx_post("/api/v5/trade/order", payload)
        
        if result.get("code") == "0":
            order_data = result.get("data", [])
            if order_data:
                order_info = order_data[0]
                order_id = order_info.get("ordId")
                s_code = order_info.get("sCode", "0")
                s_msg = order_info.get("sMsg", "")
                
                if s_code == "0":
                    print(f"✅ Order placed successfully!")
                    print(f"  🆔 Order ID: {order_id}")
                    print(f"  📝 Message: {s_msg}")
                    
                    return {
                        "success": True,
                        "orderId": order_id,
                        "instId": instId,
                        "side": side,
                        "ordType": ordType,
                        "size": sz,
                        "price": px,
                        "message": s_msg,
                        "result": result
                    }
                else:
                    print(f"❌ Order failed: {s_code} - {s_msg}")
                    return {
                        "success": False,
                        "error": f"{s_code}: {s_msg}",
                        "result": result
                    }
            else:
                print(f"❌ Order failed: No order data returned")
                return {
                    "success": False,
                    "error": "No order data returned",
                    "result": result
                }
        else:
            print(f"❌ Order failed: {result}")
            return {
                "success": False,
                "error": result.get("msg", "Unknown error"),
                "result": result
            }
            
    except Exception as e:
        print(f"❌ Error placing order: {e}")
        return {
            "success": False,
            "error": str(e),
            "orderId": None
        }


def place_options_market_order(
    instId: str,
    side: str,
    sz: int,
    reduceOnly: bool = False
) -> Dict[str, Any]:
    """
    Place a market order for options
    
    Args:
        instId: Options contract ID
        side: "buy" or "sell"
        sz: Number of contracts
        reduceOnly: Whether this is a reduce-only order
    
    Returns:
        Dict: Order result
    """
    return place_options_order(
        instId=instId,
        side=side,
        sz=sz,
        ordType="market",
        reduceOnly=reduceOnly
    )


def place_options_limit_order(
    instId: str,
    side: str,
    sz: int,
    px: float,
    reduceOnly: bool = False
) -> Dict[str, Any]:
    """
    Place a limit order for options
    
    Args:
        instId: Options contract ID
        side: "buy" or "sell"
        sz: Number of contracts
        px: Limit price
        reduceOnly: Whether this is a reduce-only order
    
    Returns:
        Dict: Order result
    """
    return place_options_order(
        instId=instId,
        side=side,
        sz=sz,
        ordType="limit",
        px=px,
        reduceOnly=reduceOnly
    )


def place_options_limit_order_relative_to_book(
    instId: str,
    side: str,
    sz: int,
    offset: float = 0.0001,  # Offset from bid/ask
    reduceOnly: bool = False
) -> Dict[str, Any]:
    """
    Place a limit order relative to current bid/ask prices
    
    Args:
        instId: Options contract ID
        side: "buy" or "sell"
        sz: Number of contracts
        offset: Price offset from bid (for buy) or ask (for sell)
        reduceOnly: Whether this is a reduce-only order
    
    Returns:
        Dict: Order result
    """
    print(f"📊 Placing limit order relative to orderbook for {instId}...")
    
    # Get current bid/ask
    bid_ask = get_options_bid_ask(instId)
    if not bid_ask:
        return {
            "success": False,
            "error": "Failed to get current bid/ask prices"
        }
    
    # Calculate limit price
    if side.lower() == "buy":
        # For buy orders, use bid + offset (slightly above current bid)
        limit_price = bid_ask["bid"] + offset
        reference_price = bid_ask["bid"]
        print(f"💰 Current bid: ${reference_price:.4f}")
        print(f"🎯 Buy limit price: ${limit_price:.4f} (bid + ${offset:.4f})")
    else:
        # For sell orders, use ask - offset (slightly below current ask)
        limit_price = bid_ask["ask"] - offset
        reference_price = bid_ask["ask"]
        print(f"💰 Current ask: ${reference_price:.4f}")
        print(f"🎯 Sell limit price: ${limit_price:.4f} (ask - ${offset:.4f})")
    
    # Place the limit order
    result = place_options_limit_order(
        instId=instId,
        side=side,
        sz=sz,
        px=limit_price,
        reduceOnly=reduceOnly
    )
    
    # Add reference price info to result
    if result.get("success"):
        result["reference_price"] = reference_price
        result["offset"] = offset
    
    return result


def get_options_positions(instType: str = "OPTION", instId: Optional[str] = None) -> List[Dict]:
    """
    Get current options positions
    
    Args:
        instType: Instrument type, default "OPTION"
        instId: Specific contract ID (optional)
    
    Returns:
        List: Current positions
    """
    print(f"🔍 Getting options positions...")
    
    try:
        params = {"instType": instType}
        if instId:
            params["instId"] = instId
        
        data = okx_get("/api/v5/account/positions", params)
        
        positions = data.get("data", [])
        
        # Filter for actual positions (non-zero)
        active_positions = []
        for pos in positions:
            position_size = float(pos.get("pos", 0))
            if position_size != 0:
                active_positions.append(pos)
                
                print(f"📊 Position: {pos.get('instId')}")
                print(f"  📏 Size: {position_size} contracts")
                print(f"  📈 Side: {'Long' if position_size > 0 else 'Short'}")
                print(f"  💰 Avg Price: ${float(pos.get('avgPx', 0)):.4f}")
                print(f"  📊 Mark Price: ${float(pos.get('markPx', 0)):.4f}")
                print(f"  💵 Unrealized PnL: ${float(pos.get('upl', 0)):.4f}")
        
        if not active_positions:
            print("📭 No active options positions found")
        
        return active_positions
        
    except Exception as e:
        print(f"❌ Error getting positions: {e}")
        return []


def close_options_position(instId: str) -> Dict[str, Any]:
    """
    Close an options position using market order
    
    Args:
        instId: Options contract ID
    
    Returns:
        Dict: Close order result
    """
    print(f"🔄 Closing position for {instId}...")
    
    # Get current position
    positions = get_options_positions(instId=instId)
    
    if not positions:
        return {
            "success": False,
            "error": f"No active position found for {instId}"
        }
    
    position = positions[0]
    position_size = float(position.get("pos", 0))
    
    if position_size == 0:
        return {
            "success": False,
            "error": f"Position size is zero for {instId}"
        }
    
    # Determine close side and size
    if position_size > 0:
        # Long position, sell to close
        close_side = "sell"
        close_size = int(abs(position_size))
    else:
        # Short position, buy to close
        close_side = "buy"
        close_size = int(abs(position_size))
    
    print(f"📤 Closing {abs(position_size)} contracts via {close_side} order")
    
    # Place market order to close
    return place_options_market_order(
        instId=instId,
        side=close_side,
        sz=close_size,
        reduceOnly=True
    )


def demo_options_trading():
    """Demonstrate options trading functionality"""
    print("🚀 Options Trading Demo\n")
    
    # This is just a demo - don't run with real money!
    print("⚠️  DEMO MODE - Using simulated trading")
    
    # Example BTC options contract (you should use real contract IDs)
    demo_contract = "BTC-USD-241227-100000-C"  # Example: BTC Call option
    
    print(f"📊 Demo contract: {demo_contract}")
    
    # 1. Get current bid/ask
    print("\n" + "=" * 50)
    print("📋 Step 1: Get current bid/ask")
    bid_ask = get_options_bid_ask(demo_contract)
    
    if bid_ask:
        print(f"💰 Bid: ${bid_ask['bid']:.4f}")
        print(f"💰 Ask: ${bid_ask['ask']:.4f}")
        print(f"📊 Spread: ${bid_ask['spread']:.4f}")
    
    # 2. Check current positions
    print("\n" + "=" * 50)
    print("🔍 Step 2: Check current positions")
    positions = get_options_positions()
    
    # 3. Demo order placement (commented out for safety)
    print("\n" + "=" * 50)
    print("📝 Step 3: Demo order placement")
    print("⚠️  Order placement is commented out for safety")
    print("Uncomment the code below to place actual orders:")
    
    print("""
    # Example: Place a limit buy order
    # result = place_options_limit_order_relative_to_book(
    #     instId=demo_contract,
    #     side="buy",
    #     sz=1,
    #     offset=0.0001
    # )
    
    # Example: Place a market sell order
    # result = place_options_market_order(
    #     instId=demo_contract,
    #     side="sell",
    #     sz=1
    # )
    """)
    
    print("\n✅ Demo completed!")
    
    return {
        "demo_contract": demo_contract,
        "bid_ask": bid_ask,
        "positions": positions
    }


if __name__ == "__main__":
    # Run demo
    demo_result = demo_options_trading()
    
    print("\n📝 Available functions:")
    print("  - place_options_order(instId, side, sz, ordType, px, ...)")
    print("  - place_options_market_order(instId, side, sz)")
    print("  - place_options_limit_order(instId, side, sz, px)")
    print("  - place_options_limit_order_relative_to_book(instId, side, sz, offset)")
    print("  - get_options_positions(instType, instId)")
    print("  - close_options_position(instId)")
    print("  - get_options_bid_ask(instId)")
