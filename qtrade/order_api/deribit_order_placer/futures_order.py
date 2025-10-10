#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deribit Futures Order Placement Module
Support placing market/limit orders for BTC/ETH futures and managing orders
"""

import requests
from typing import Literal, Dict, Any, List, Optional, Union
from datetime import datetime
import time

# Import API credentials
from qtrade.order_api.deribit_order_placer import api_config

DERIBIT_BASE = {
    "testnet": "https://test.deribit.com",
    "mainnet": "https://www.deribit.com",
}

Currency = Literal["BTC", "ETH"]
Env = Literal["testnet", "mainnet"]
OrderType = Literal["market", "limit"]
Side = Literal["buy", "sell"]

class DeribitAPIError(Exception):
    pass


def get_access_token(env: Env = "testnet") -> str:
    """
    Get access token for authenticated API calls
    """
    base = DERIBIT_BASE[env]
    url = f"{base}/api/v2/public/auth"
    
    response = requests.get(url, params=api_config)
    response.raise_for_status()
    
    data = response.json()
    
    if data.get("error"):
        raise DeribitAPIError(f"Authentication failed: {data['error']}")
    
    result = data.get("result", {})
    access_token = result.get("access_token")
    
    if not access_token:
        raise DeribitAPIError("No access token received")
    
    return access_token


def _authenticated_request(method: str, path: str, params: Dict[str, Any] = None, env: Env = "testnet") -> Dict[str, Any]:
    """
    Make authenticated request to Deribit API
    """
    base = DERIBIT_BASE[env]
    access_token = get_access_token(env)
    
    url = f"{base}/api/v2/{path}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    if params is None:
        params = {}
    
    if method.upper() == "GET":
        response = requests.get(url, headers=headers, params=params)
    elif method.upper() == "POST":
        response = requests.post(url, headers=headers, json=params)
    else:
        raise ValueError(f"Unsupported method: {method}")
    
    response.raise_for_status()
    
    data = response.json()
    
    if data.get("error"):
        raise DeribitAPIError(f"API Error: {data['error']}")
    
    return data.get("result", {})


def get_current_price(instrument: str, env: Env = "testnet") -> Dict[str, Any]:
    """
    Get current market price for an instrument
    
    Args:
        instrument: e.g., "BTC-PERPETUAL", "ETH-PERPETUAL"
        env: "testnet" or "mainnet"
    
    Returns:
        Dict with current price information
    """
    try:
        base = DERIBIT_BASE[env]
        url = f"{base}/api/v2/public/ticker"
        
        response = requests.get(url, params={"instrument_name": instrument})
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("error"):
            raise DeribitAPIError(f"Price fetch error: {data['error']}")
        
        result = data.get("result", {})
        
        return {
            "instrument": instrument,
            "mark_price": result.get("mark_price"),
            "index_price": result.get("index_price"),
            "best_bid": result.get("best_bid_price"),
            "best_ask": result.get("best_ask_price"),
            "last_price": result.get("last_price"),
            "timestamp": result.get("timestamp")
        }
        
    except Exception as e:
        print(f"❌ Error getting price for {instrument}: {e}")
        return {}


def place_futures_order(
    instrument: str,
    side: Side,
    amount: Union[int, float],
    order_type: OrderType = "market",
    price: Optional[float] = None,
    time_in_force: str = "good_til_cancelled",
    reduce_only: bool = False,
    post_only: bool = False,
    env: Env = "testnet"
) -> Dict[str, Any]:
    """
    Place a futures order
    
    Args:
        instrument: e.g., "BTC-PERPETUAL", "ETH-PERPETUAL"
        side: "buy" or "sell"
        amount: Order size (contracts for futures)
        order_type: "market" or "limit"
        price: Price for limit orders (required for limit orders)
        time_in_force: "good_til_cancelled", "fill_or_kill", "immediate_or_cancel"
        reduce_only: Whether this is a reduce-only order
        post_only: Whether this is a post-only order (maker only)
        env: "testnet" or "mainnet"
    
    Returns:
        Dict with order result
    """
    print(f"📝 Placing {order_type} {side} order for {instrument}...")
    
    # Validate inputs
    if order_type == "limit" and price is None:
        raise ValueError("Price is required for limit orders")
    
    if amount <= 0:
        raise ValueError("Amount must be positive")
    
    # Get current market data for reference
    market_data = get_current_price(instrument, env)
    
    if market_data:
        print(f"💰 Current market:")
        print(f"   Mark Price: ${market_data.get('mark_price', 0):,.2f}")
        print(f"   Best Bid: ${market_data.get('best_bid', 0):,.2f}")
        print(f"   Best Ask: ${market_data.get('best_ask', 0):,.2f}")
    
    # Build order parameters for Deribit API
    params = {
        "instrument_name": instrument,
        "amount": int(amount) if amount == int(amount) else amount,
        "type": order_type
    }
    
    # Add price for limit orders
    if order_type == "limit" and price is not None:
        params["price"] = int(price) if price == int(price) else price
        print(f"🎯 Limit price: ${price:,.2f}")
    
    # Add optional parameters
    if time_in_force != "good_til_cancelled":
        params["time_in_force"] = time_in_force
    
    if reduce_only:
        params["reduce_only"] = "true"
    
    if post_only:
        params["post_only"] = "true"
    
    print(f"📊 Order details:")
    print(f"   Instrument: {instrument}")
    print(f"   Side: {side.upper()}")
    print(f"   Amount: {amount}")
    print(f"   Type: {order_type.upper()}")
    
    try:
        # Use the correct Deribit endpoint for order placement
        endpoint = "private/buy" if side == "buy" else "private/sell"
        
        result = _authenticated_request("GET", endpoint, params, env)
        
        if result and "order" in result:
            order_info = result["order"]
            order_id = order_info.get("order_id")
            order_state = order_info.get("order_state")
            filled_amount = order_info.get("filled_amount", 0)
            
            print(f"✅ Order placed successfully!")
            print(f"   🆔 Order ID: {order_id}")
            print(f"   📊 State: {order_state}")
            print(f"   ✅ Filled: {filled_amount}")
            
            return {
                "success": True,
                "order_id": order_id,
                "order_state": order_state,
                "filled_amount": filled_amount,
                "instrument": instrument,
                "side": side,
                "amount": amount,
                "order_type": order_type,
                "price": price,
                "result": result
            }
        else:
            print(f"❌ Order placement failed: Unexpected response format")
            return {
                "success": False,
                "error": "Unexpected response format",
                "result": result
            }
            
    except Exception as e:
        print(f"❌ Error placing order: {e}")
        return {
            "success": False,
            "error": str(e),
            "order_id": None
        }


def place_market_order(
    instrument: str,
    side: Side,
    amount: Union[int, float],
    reduce_only: bool = False,
    env: Env = "testnet"
) -> Dict[str, Any]:
    """
    Place a market order (convenience function)
    
    Args:
        instrument: e.g., "BTC-PERPETUAL", "ETH-PERPETUAL"
        side: "buy" or "sell"
        amount: Order size
        reduce_only: Whether this is a reduce-only order
        env: "testnet" or "mainnet"
    
    Returns:
        Dict with order result
    """
    return place_futures_order(
        instrument=instrument,
        side=side,
        amount=amount,
        order_type="market",
        reduce_only=reduce_only,
        env=env
    )


def place_limit_order(
    instrument: str,
    side: Side,
    amount: Union[int, float],
    price: float,
    post_only: bool = False,
    reduce_only: bool = False,
    env: Env = "testnet"
) -> Dict[str, Any]:
    """
    Place a limit order (convenience function)
    
    Args:
        instrument: e.g., "BTC-PERPETUAL", "ETH-PERPETUAL"
        side: "buy" or "sell"
        amount: Order size
        price: Limit price
        post_only: Whether this is a post-only order (maker only)
        reduce_only: Whether this is a reduce-only order
        env: "testnet" or "mainnet"
    
    Returns:
        Dict with order result
    """
    return place_futures_order(
        instrument=instrument,
        side=side,
        amount=amount,
        order_type="limit",
        price=price,
        post_only=post_only,
        reduce_only=reduce_only,
        env=env
    )


def place_limit_order_relative_to_market(
    instrument: str,
    side: Side,
    amount: Union[int, float],
    offset: float = 10.0,  # USD offset from best bid/ask
    post_only: bool = True,
    env: Env = "testnet"
) -> Dict[str, Any]:
    """
    Place a limit order relative to current market prices
    
    Args:
        instrument: e.g., "BTC-PERPETUAL", "ETH-PERPETUAL"
        side: "buy" or "sell"
        amount: Order size
        offset: Price offset from best bid (for buy) or ask (for sell)
        post_only: Whether this is a post-only order
        env: "testnet" or "mainnet"
    
    Returns:
        Dict with order result
    """
    print(f"📊 Placing limit order relative to market for {instrument}...")
    
    # Get current market data
    market_data = get_current_price(instrument, env)
    
    if not market_data:
        return {
            "success": False,
            "error": "Failed to get current market data"
        }
    
    best_bid = market_data.get("best_bid")
    best_ask = market_data.get("best_ask")
    
    if not best_bid or not best_ask:
        return {
            "success": False,
            "error": "No valid bid/ask prices available"
        }
    
    # Calculate limit price
    if side == "buy":
        # For buy orders, place below current ask (bid + offset)
        limit_price = best_bid + offset
        reference_price = best_bid
        print(f"💰 Current bid: ${reference_price:,.2f}")
        print(f"🎯 Buy limit price: ${limit_price:,.2f} (bid + ${offset:,.2f})")
    else:
        # For sell orders, place above current bid (ask - offset)
        limit_price = best_ask - offset
        reference_price = best_ask
        print(f"💰 Current ask: ${reference_price:,.2f}")
        print(f"🎯 Sell limit price: ${limit_price:,.2f} (ask - ${offset:,.2f})")
    
    # Place the limit order
    result = place_limit_order(
        instrument=instrument,
        side=side,
        amount=amount,
        price=limit_price,
        post_only=post_only,
        env=env
    )
    
    # Add reference price info to result
    if result.get("success"):
        result["reference_price"] = reference_price
        result["offset"] = offset
    
    return result


def get_order_status(order_id: str, env: Env = "testnet") -> Dict[str, Any]:
    """
    Get status of a specific order
    
    Args:
        order_id: Order ID to check
        env: "testnet" or "mainnet"
    
    Returns:
        Dict with order status information
    """
    print(f"🔍 Checking status of order {order_id}...")
    
    try:
        params = {"order_id": order_id}
        result = _authenticated_request("GET", "private/get_order_state", params, env)
        
        if result:
            order_state = result.get("order_state")
            filled_amount = result.get("filled_amount", 0)
            remaining_amount = result.get("amount", 0) - filled_amount
            
            print(f"📊 Order Status:")
            print(f"   🆔 Order ID: {order_id}")
            print(f"   📊 State: {order_state}")
            print(f"   ✅ Filled: {filled_amount}")
            print(f"   ⏳ Remaining: {remaining_amount}")
            
            return result
        else:
            print(f"❌ Order not found: {order_id}")
            return {}
            
    except Exception as e:
        print(f"❌ Error checking order status: {e}")
        return {"error": str(e)}


def cancel_order(order_id: str, env: Env = "testnet") -> Dict[str, Any]:
    """
    Cancel a specific order
    
    Args:
        order_id: Order ID to cancel
        env: "testnet" or "mainnet"
    
    Returns:
        Dict with cancellation result
    """
    print(f"🚫 Canceling order {order_id}...")
    
    try:
        params = {"order_id": order_id}
        result = _authenticated_request("GET", "private/cancel", params, env)
        
        if result:
            order_id_result = result.get("order_id")
            
            print(f"✅ Order canceled successfully!")
            print(f"   🆔 Canceled Order ID: {order_id_result}")
            
            return {
                "success": True,
                "order_id": order_id_result,
                "result": result
            }
        else:
            print(f"❌ Failed to cancel order")
            return {
                "success": False,
                "error": "No result returned"
            }
            
    except Exception as e:
        print(f"❌ Error canceling order: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def cancel_all_orders(instrument: str = None, env: Env = "testnet") -> Dict[str, Any]:
    """
    Cancel all open orders (optionally filtered by instrument)
    
    Args:
        instrument: Optional instrument filter (e.g., "BTC-PERPETUAL")
        env: "testnet" or "mainnet"
    
    Returns:
        Dict with cancellation results
    """
    print(f"🚨 Canceling all orders{f' for {instrument}' if instrument else ''}...")
    
    try:
        params = {}
        if instrument:
            params["instrument_name"] = instrument
        
        result = _authenticated_request("POST", "private/cancel_all", params, env)
        
        if result is not None:
            canceled_count = result if isinstance(result, int) else len(result) if isinstance(result, list) else 1
            
            print(f"✅ Canceled {canceled_count} orders successfully!")
            
            return {
                "success": True,
                "canceled_count": canceled_count,
                "result": result
            }
        else:
            print(f"❌ Failed to cancel orders")
            return {
                "success": False,
                "error": "No result returned"
            }
            
    except Exception as e:
        print(f"❌ Error canceling orders: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def get_open_orders(instrument: str = None, env: Env = "testnet") -> List[Dict[str, Any]]:
    """
    Get all open orders (optionally filtered by instrument)
    
    Args:
        instrument: Optional instrument filter
        env: "testnet" or "mainnet"
    
    Returns:
        List of open orders
    """
    print(f"📝 Getting open orders{f' for {instrument}' if instrument else ''}...")
    
    try:
        params = {}
        if instrument:
            params["instrument_name"] = instrument
        
        result = _authenticated_request("GET", "private/get_open_orders", params, env)
        
        if not result:
            print("📭 No open orders found")
            return []
        
        orders = result if isinstance(result, list) else [result]
        
        print(f"✅ Found {len(orders)} open orders:")
        
        for i, order in enumerate(orders):
            order_id = order.get("order_id")
            instrument_name = order.get("instrument_name")
            direction = order.get("direction")
            amount = order.get("amount", 0)
            price = order.get("price")
            order_type = order.get("order_type")
            order_state = order.get("order_state")
            
            print(f"\n   📋 Order {i+1}: {order_id}")
            print(f"      Instrument: {instrument_name}")
            print(f"      Direction: {direction}")
            print(f"      Amount: {amount}")
            print(f"      Price: ${price:,.2f}" if price else "      Price: Market")
            print(f"      Type: {order_type}")
            print(f"      State: {order_state}")
        
        return orders
        
    except Exception as e:
        print(f"❌ Error getting open orders: {e}")
        return []


def place_market_order_btc_notional(
    instrument: str,
    side: Side,
    btc_amount: float,
    reduce_only: bool = False,
    env: Env = "testnet"
) -> Dict[str, Any]:
    """
    Place a market order with BTC notional amount
    
    Args:
        instrument: e.g., "BTC-PERPETUAL", "ETH-PERPETUAL"
        side: "buy" or "sell"
        btc_amount: Amount in BTC (e.g., 0.0001 for 0.0001 BTC)
        reduce_only: Whether this is a reduce-only order
        env: "testnet" or "mainnet"
    
    Returns:
        Dict with order result including conversion info
    """
    print(f"🟠 Placing market order with BTC notional...")
    
    # Get current price for conversion
    price_data = get_current_price(instrument, env)
    
    if not price_data:
        return {
            "success": False,
            "error": "Failed to get current market price for conversion"
        }
    
    current_price = price_data.get("mark_price", 0)
    
    if current_price <= 0:
        return {
            "success": False,
            "error": "Invalid current price for conversion"
        }
    
    # Convert BTC to USD and round to nearest multiple of 10 (Deribit requirement)
    usd_amount_raw = btc_amount * current_price
    usd_amount = round(usd_amount_raw / 10) * 10
    
    # Validate minimum order size ($10 USD)
    if usd_amount < 10:
        return {
            "success": False,
            "error": f"Order size too small: ${usd_amount} (minimum $10 USD)"
        }
    
    print(f"🔄 BTC→USD Conversion:")
    print(f"   BTC Amount: {btc_amount} BTC")
    print(f"   Current Price: ${current_price:,.2f}")
    print(f"   USD Amount: ${usd_amount} (rounded to multiple of 10)")
    
    # Place the market order with USD amount
    result = place_market_order(
        instrument=instrument,
        side=side,
        amount=usd_amount,
        reduce_only=reduce_only,
        env=env
    )
    
    # Add conversion info to result
    if result.get("success"):
        result["btc_amount"] = btc_amount
        result["conversion_price"] = current_price
        result["usd_amount"] = usd_amount
    
    return result


def place_limit_order_btc_notional(
    instrument: str,
    side: Side,
    btc_amount: float,
    price: float,
    post_only: bool = False,
    reduce_only: bool = False,
    env: Env = "testnet"
) -> Dict[str, Any]:
    """
    Place a limit order with BTC notional amount
    
    Args:
        instrument: e.g., "BTC-PERPETUAL", "ETH-PERPETUAL"
        side: "buy" or "sell"
        btc_amount: Amount in BTC (e.g., 0.0001 for 0.0001 BTC)
        price: Limit price in USD
        post_only: Whether this is a post-only order (maker only)
        reduce_only: Whether this is a reduce-only order
        env: "testnet" or "mainnet"
    
    Returns:
        Dict with order result including conversion info
    """
    print(f"🟠 Placing limit order with BTC notional...")
    
    # Get current price for conversion
    price_data = get_current_price(instrument, env)
    
    if not price_data:
        return {
            "success": False,
            "error": "Failed to get current market price for conversion"
        }
    
    current_price = price_data.get("mark_price", 0)
    
    if current_price <= 0:
        return {
            "success": False,
            "error": "Invalid current price for conversion"
        }
    
    # Convert BTC to USD and round to nearest multiple of 10 (Deribit requirement)
    usd_amount_raw = btc_amount * current_price
    usd_amount = round(usd_amount_raw / 10) * 10
    
    # Validate minimum order size ($10 USD)
    if usd_amount < 10:
        return {
            "success": False,
            "error": f"Order size too small: ${usd_amount} (minimum $10 USD)"
        }
    
    print(f"🔄 BTC→USD Conversion:")
    print(f"   BTC Amount: {btc_amount} BTC")
    print(f"   Current Price: ${current_price:,.2f}")
    print(f"   USD Amount: ${usd_amount} (rounded to multiple of 10)")
    print(f"   Limit Price: ${price:,.2f}")
    
    # Place the limit order with USD amount
    result = place_limit_order(
        instrument=instrument,
        side=side,
        amount=usd_amount,
        price=price,
        post_only=post_only,
        reduce_only=reduce_only,
        env=env
    )
    
    # Add conversion info to result
    if result.get("success"):
        result["btc_amount"] = btc_amount
        result["conversion_price"] = current_price
        result["usd_amount"] = usd_amount
    
    return result


def place_limit_order_btc_relative_to_market(
    instrument: str,
    side: Side,
    btc_amount: float,
    offset: float = 10.0,  # USD offset from best bid/ask
    post_only: bool = True,
    env: Env = "testnet"
) -> Dict[str, Any]:
    """
    Place a limit order with BTC notional amount relative to current market prices
    
    Args:
        instrument: e.g., "BTC-PERPETUAL", "ETH-PERPETUAL"
        side: "buy" or "sell"
        btc_amount: Amount in BTC (e.g., 0.0001 for 0.0001 BTC)
        offset: Price offset from best bid (for buy) or ask (for sell)
        post_only: Whether this is a post-only order
        env: "testnet" or "mainnet"
    
    Returns:
        Dict with order result including conversion info
    """
    print(f"🟠 Placing BTC notional limit order relative to market...")
    
    # Get current price for conversion and limit price calculation
    price_data = get_current_price(instrument, env)
    
    if not price_data:
        return {
            "success": False,
            "error": "Failed to get current market price"
        }
    
    current_price = price_data.get("mark_price", 0)
    best_bid = price_data.get("best_bid")
    best_ask = price_data.get("best_ask")
    
    if not best_bid or not best_ask or current_price <= 0:
        return {
            "success": False,
            "error": "Invalid market data for order placement"
        }
    
    # Calculate limit price
    if side == "buy":
        limit_price = best_bid + offset
        reference_price = best_bid
    else:
        limit_price = best_ask - offset
        reference_price = best_ask
    
    # Convert BTC to USD and round to nearest multiple of 10 (Deribit requirement)
    usd_amount_raw = btc_amount * current_price
    usd_amount = round(usd_amount_raw / 10) * 10
    
    # Validate minimum order size
    if usd_amount < 10:
        return {
            "success": False,
            "error": f"Order size too small: ${usd_amount} (minimum $10 USD)"
        }
    
    print(f"🔄 BTC→USD Conversion:")
    print(f"   BTC Amount: {btc_amount} BTC")
    print(f"   Current Price: ${current_price:,.2f}")
    print(f"   USD Amount: ${usd_amount} (rounded to multiple of 10)")
    print(f"💰 Market relative pricing:")
    print(f"   Reference ({side}): ${reference_price:,.2f}")
    print(f"   Limit Price: ${limit_price:,.2f} (offset: ${offset:+.2f})")
    
    # Place the limit order
    result = place_limit_order(
        instrument=instrument,
        side=side,
        amount=usd_amount,
        price=limit_price,
        post_only=post_only,
        env=env
    )
    
    # Add conversion and market info to result
    if result.get("success"):
        result["btc_amount"] = btc_amount
        result["conversion_price"] = current_price
        result["usd_amount"] = usd_amount
        result["reference_price"] = reference_price
        result["offset"] = offset
    
    return result


def demo_futures_trading():
    """
    Demonstrate futures trading functionality
    """
    print("🚀 Deribit Futures Trading Demo")
    print("=" * 60)
    print("⚠️  DEMO MODE - Using testnet environment")
    
    try:
        # Test instrument
        instrument = "BTC-PERPETUAL"
        
        # 1. Get current price
        print(f"\n📊 Step 1: Get current price for {instrument}")
        price_data = get_current_price(instrument, "testnet")
        
        if not price_data:
            print("❌ Cannot get price data")
            return
        
        current_price = price_data.get("mark_price", 0)
        
        # 2. Check open orders
        print(f"\n📝 Step 2: Check existing open orders")
        existing_orders = get_open_orders(instrument, "testnet")
        
        # 3. Demo order placement (commented for safety)
        print(f"\n📝 Step 3: Demo order placement")
        print("⚠️  Order placement is commented out for safety")
        print("Uncomment the code below to place actual orders:")
        
        limit_price = current_price - 1000  # $1000 below market
        
        print(f"""
# Example 1: Market Buy Order
market_result = place_market_order(
    instrument="{instrument}",
    side="buy",
    amount=10  # 10 contracts
)

# Example 2: Limit Sell Order
limit_result = place_limit_order(
    instrument="{instrument}",
    side="sell", 
    amount=10,
    price={limit_price:.0f}  # ${limit_price:.0f}
)

# Example 3: Smart Limit Order
smart_result = place_limit_order_relative_to_market(
    instrument="{instrument}",
    side="buy",
    amount=5,
    offset=50.0  # $50 below best bid
)

# Example 4: Check Order Status
if limit_result.get('success'):
    order_status = get_order_status(limit_result['order_id'])

# Example 5: Cancel Order
if limit_result.get('success'):
    cancel_result = cancel_order(limit_result['order_id'])

# ========== NEW: BTC NOTIONAL FUNCTIONS ==========

# Example 6: BTC Notional Market Order
btc_market_result = place_market_order_btc_notional(
    instrument="{instrument}",
    side="buy",
    btc_amount=0.0001  # 0.0001 BTC notional
)

# Example 7: BTC Notional Limit Order
btc_limit_result = place_limit_order_btc_notional(
    instrument="{instrument}",
    side="sell",
    btc_amount=0.0001,  # 0.0001 BTC notional
    price={limit_price:.0f}  # ${limit_price:.0f}
)

# Example 8: BTC Notional Smart Limit Order
btc_smart_result = place_limit_order_btc_relative_to_market(
    instrument="{instrument}",
    side="buy",
    btc_amount=0.0001,  # 0.0001 BTC notional
    offset=50.0  # $50 below best bid
)
""")
        
        print(f"\n✅ Demo completed!")
        print(f"💡 Current {instrument} price: ${current_price:,.2f}")
        print(f"📋 Existing orders: {len(existing_orders)}")
        print(f"🟠 NEW: BTC notional functions available!")
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    demo_futures_trading()
