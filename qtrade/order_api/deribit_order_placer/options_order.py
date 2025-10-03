#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deribit Options Order Placement Module
Support placing market/limit orders for BTC/ETH options and managing orders
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


def get_options_instruments(currency: Currency = "BTC", expired: bool = False, env: Env = "testnet") -> List[Dict[str, Any]]:
    """
    Get available options instruments
    
    Args:
        currency: "BTC" or "ETH"
        expired: Include expired options
        env: "testnet" or "mainnet"
    
    Returns:
        List of options instruments
    """
    try:
        base = DERIBIT_BASE[env]
        url = f"{base}/api/v2/public/get_instruments"
        
        params = {
            "currency": currency,
            "kind": "option",
            "expired": "true" if expired else "false"
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("error"):
            raise DeribitAPIError(f"Error getting instruments: {data['error']}")
        
        instruments = data.get("result", [])
        print(f"✅ Found {len(instruments)} {currency} options instruments")
        
        return instruments
        
    except Exception as e:
        print(f"❌ Error getting options instruments: {e}")
        return []


def get_options_orderbook(instrument: str, depth: int = 5, env: Env = "testnet") -> Dict[str, Any]:
    """
    Get options orderbook data
    
    Args:
        instrument: Options instrument name (e.g., "BTC-25JAN25-100000-C")
        depth: Orderbook depth
        env: "testnet" or "mainnet"
    
    Returns:
        Dict with orderbook data
    """
    try:
        base = DERIBIT_BASE[env]
        url = f"{base}/api/v2/public/get_order_book"
        
        params = {
            "instrument_name": instrument,
            "depth": depth
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("error"):
            raise DeribitAPIError(f"Error getting orderbook: {data['error']}")
        
        result = data.get("result", {})
        
        bids = result.get("bids", [])
        asks = result.get("asks", [])
        
        best_bid = bids[0][0] if bids else 0
        best_ask = asks[0][0] if asks else 0
        
        return {
            "instrument": instrument,
            "bids": bids,
            "asks": asks,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": best_ask - best_bid if best_bid > 0 and best_ask > 0 else 0,
            "mid_price": (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else 0,
            "timestamp": result.get("timestamp", "")
        }
        
    except Exception as e:
        print(f"❌ Error getting orderbook for {instrument}: {e}")
        return {}


def place_options_order(
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
    Place an options order
    
    Args:
        instrument: Options instrument name (e.g., "BTC-25JAN25-100000-C")
        side: "buy" or "sell"
        amount: Order size (number of contracts)
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
    orderbook = get_options_orderbook(instrument, env=env)
    
    if orderbook:
        print(f"💰 Current market:")
        print(f"   Best Bid: {orderbook.get('best_bid', 0):.4f}")
        print(f"   Best Ask: {orderbook.get('best_ask', 0):.4f}")
        print(f"   Spread: {orderbook.get('spread', 0):.4f}")
    
    # Build order parameters for Deribit API
    params = {
        "instrument_name": instrument,
        "amount": amount,
        "type": order_type
    }
    
    # Add price for limit orders
    if order_type == "limit" and price is not None:
        params["price"] = price
        print(f"🎯 Limit price: {price:.4f}")
    
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
    print(f"   Amount: {amount} contracts")
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
            
            print(f"✅ Options order placed successfully!")
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
            print(f"❌ Options order placement failed: Unexpected response format")
            return {
                "success": False,
                "error": "Unexpected response format",
                "result": result
            }
            
    except Exception as e:
        print(f"❌ Error placing options order: {e}")
        return {
            "success": False,
            "error": str(e),
            "order_id": None
        }


def place_options_market_order(
    instrument: str,
    side: Side,
    amount: Union[int, float],
    reduce_only: bool = False,
    env: Env = "testnet"
) -> Dict[str, Any]:
    """
    Place an options market order (convenience function)
    
    Args:
        instrument: Options instrument name
        side: "buy" or "sell"
        amount: Order size (number of contracts)
        reduce_only: Whether this is a reduce-only order
        env: "testnet" or "mainnet"
    
    Returns:
        Dict with order result
    """
    return place_options_order(
        instrument=instrument,
        side=side,
        amount=amount,
        order_type="market",
        reduce_only=reduce_only,
        env=env
    )


def place_options_limit_order(
    instrument: str,
    side: Side,
    amount: Union[int, float],
    price: float,
    post_only: bool = False,
    reduce_only: bool = False,
    env: Env = "testnet"
) -> Dict[str, Any]:
    """
    Place an options limit order (convenience function)
    
    Args:
        instrument: Options instrument name
        side: "buy" or "sell"
        amount: Order size (number of contracts)
        price: Limit price
        post_only: Whether this is a post-only order (maker only)
        reduce_only: Whether this is a reduce-only order
        env: "testnet" or "mainnet"
    
    Returns:
        Dict with order result
    """
    return place_options_order(
        instrument=instrument,
        side=side,
        amount=amount,
        order_type="limit",
        price=price,
        post_only=post_only,
        reduce_only=reduce_only,
        env=env
    )


def place_options_limit_order_relative_to_market(
    instrument: str,
    side: Side,
    amount: Union[int, float],
    offset: float = 0.001,  # Price offset from best bid/ask
    post_only: bool = True,
    env: Env = "testnet"
) -> Dict[str, Any]:
    """
    Place an options limit order relative to current market prices
    
    Args:
        instrument: Options instrument name
        side: "buy" or "sell"
        amount: Order size (number of contracts)
        offset: Price offset from best bid (for buy) or ask (for sell)
        post_only: Whether this is a post-only order
        env: "testnet" or "mainnet"
    
    Returns:
        Dict with order result
    """
    print(f"📊 Placing options limit order relative to market for {instrument}...")
    
    # Get current market data
    orderbook = get_options_orderbook(instrument, env=env)
    
    if not orderbook:
        return {
            "success": False,
            "error": "Failed to get current market data"
        }
    
    best_bid = orderbook.get("best_bid")
    best_ask = orderbook.get("best_ask")
    
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
        print(f"💰 Current bid: {reference_price:.4f}")
        print(f"🎯 Buy limit price: {limit_price:.4f} (bid + {offset:.4f})")
    else:
        # For sell orders, place above current bid (ask - offset)
        limit_price = best_ask - offset
        reference_price = best_ask
        print(f"💰 Current ask: {reference_price:.4f}")
        print(f"🎯 Sell limit price: {limit_price:.4f} (ask - {offset:.4f})")
    
    # Place the limit order
    result = place_options_limit_order(
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


def get_options_order_status(order_id: str, env: Env = "testnet") -> Dict[str, Any]:
    """
    Get status of a specific options order
    
    Args:
        order_id: Order ID to check
        env: "testnet" or "mainnet"
    
    Returns:
        Dict with order status information
    """
    print(f"🔍 Checking status of options order {order_id}...")
    
    try:
        params = {"order_id": order_id}
        result = _authenticated_request("GET", "private/get_order_state", params, env)
        
        if result:
            order_state = result.get("order_state")
            filled_amount = result.get("filled_amount", 0)
            remaining_amount = result.get("amount", 0) - filled_amount
            
            print(f"📊 Options Order Status:")
            print(f"   🆔 Order ID: {order_id}")
            print(f"   📊 State: {order_state}")
            print(f"   ✅ Filled: {filled_amount}")
            print(f"   ⏳ Remaining: {remaining_amount}")
            
            return result
        else:
            print(f"❌ Options order not found: {order_id}")
            return {}
            
    except Exception as e:
        print(f"❌ Error checking options order status: {e}")
        return {"error": str(e)}


def cancel_options_order(order_id: str, env: Env = "testnet") -> Dict[str, Any]:
    """
    Cancel a specific options order
    
    Args:
        order_id: Order ID to cancel
        env: "testnet" or "mainnet"
    
    Returns:
        Dict with cancellation result
    """
    print(f"🚫 Canceling options order {order_id}...")
    
    try:
        params = {"order_id": order_id}
        result = _authenticated_request("GET", "private/cancel", params, env)
        
        if result:
            order_id_result = result.get("order_id")
            
            print(f"✅ Options order canceled successfully!")
            print(f"   🆔 Canceled Order ID: {order_id_result}")
            
            return {
                "success": True,
                "order_id": order_id_result,
                "result": result
            }
        else:
            print(f"❌ Failed to cancel options order")
            return {
                "success": False,
                "error": "No result returned"
            }
            
    except Exception as e:
        print(f"❌ Error canceling options order: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def cancel_all_options_orders(currency: Currency = None, env: Env = "testnet") -> Dict[str, Any]:
    """
    Cancel all open options orders (optionally filtered by currency)
    
    Args:
        currency: Optional currency filter ("BTC" or "ETH")
        env: "testnet" or "mainnet"
    
    Returns:
        Dict with cancellation results
    """
    print(f"🚨 Canceling all options orders{f' for {currency}' if currency else ''}...")
    
    try:
        params = {"kind": "option"}
        if currency:
            params["currency"] = currency
        
        result = _authenticated_request("POST", "private/cancel_all_by_currency", params, env)
        
        if result is not None:
            canceled_count = result if isinstance(result, int) else len(result) if isinstance(result, list) else 1
            
            print(f"✅ Canceled {canceled_count} options orders successfully!")
            
            return {
                "success": True,
                "canceled_count": canceled_count,
                "result": result
            }
        else:
            print(f"❌ Failed to cancel options orders")
            return {
                "success": False,
                "error": "No result returned"
            }
            
    except Exception as e:
        print(f"❌ Error canceling options orders: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def get_options_positions(currency: Currency = None, env: Env = "testnet") -> List[Dict[str, Any]]:
    """
    Get current options positions
    
    Args:
        currency: Optional currency filter ("BTC" or "ETH")
        env: "testnet" or "mainnet"
    
    Returns:
        List of options positions
    """
    print(f"📊 Getting options positions{f' for {currency}' if currency else ''}...")
    
    try:
        params = {"kind": "option"}
        if currency:
            params["currency"] = currency
        
        result = _authenticated_request("GET", "private/get_positions", params, env)
        
        if not result:
            print("📭 No options positions found")
            return []
        
        positions = result if isinstance(result, list) else [result]
        
        print(f"✅ Found {len(positions)} options positions:")
        
        for i, pos in enumerate(positions):
            instrument = pos.get("instrument_name", "Unknown")
            size = pos.get("size", 0)
            direction = pos.get("direction", "unknown")
            mark_price = pos.get("mark_price", 0)
            unrealized_pnl = pos.get("unrealized_pnl", 0)
            
            print(f"\n   📋 Position {i+1}: {instrument}")
            print(f"      Size: {size} contracts")
            print(f"      Direction: {direction}")
            print(f"      Mark Price: {mark_price:.4f}")
            print(f"      Unrealized PnL: {unrealized_pnl:.8f}")
        
        return positions
        
    except Exception as e:
        print(f"❌ Error getting options positions: {e}")
        return []


def get_open_options_orders(currency: Currency = None, env: Env = "testnet") -> List[Dict[str, Any]]:
    """
    Get all open options orders (optionally filtered by currency)
    
    Args:
        currency: Optional currency filter
        env: "testnet" or "mainnet"
    
    Returns:
        List of open options orders
    """
    print(f"📝 Getting open options orders{f' for {currency}' if currency else ''}...")
    
    try:
        params = {"kind": "option"}
        if currency:
            params["currency"] = currency
        
        result = _authenticated_request("GET", "private/get_open_orders", params, env)
        
        if not result:
            print("📭 No open options orders found")
            return []
        
        orders = result if isinstance(result, list) else [result]
        
        print(f"✅ Found {len(orders)} open options orders:")
        
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
            print(f"      Amount: {amount} contracts")
            print(f"      Price: {price:.4f}" if price else "      Price: Market")
            print(f"      Type: {order_type}")
            print(f"      State: {order_state}")
        
        return orders
        
    except Exception as e:
        print(f"❌ Error getting open options orders: {e}")
        return []


def find_atm_options(currency: Currency = "BTC", 
                     days_to_expiry: int = 7, 
                     env: Env = "testnet",
                     max_options: int = 5) -> Dict[str, Any]:
    """
    Find at-the-money (ATM) options for a given currency
    
    Args:
        currency: "BTC" or "ETH"
        days_to_expiry: Preferred days to expiry
        env: "testnet" or "mainnet"
    
    Returns:
        Dict with ATM call and put options
    """
    print(f"🎯 Finding ATM {currency} options...")
    
    try:
        # Get current index price
        from .options_orderbook import get_index_price
        current_price = get_index_price(currency, env)
        
        if not current_price:
            return {"error": "Could not get current price"}
        
        print(f"📊 Current {currency} price: ${current_price:,.2f}")
        
        # Get available options
        instruments = get_options_instruments(currency, expired=False, env=env)
        
        if not instruments:
            return {"error": "No options instruments found"}
        
        # Find options closest to current price and desired expiry
        atm_options = []
        
        for instrument in instruments:
            instrument_name = instrument.get("instrument_name", "")
            strike = instrument.get("strike")
            expiration_timestamp = instrument.get("expiration_timestamp")
            
            if not strike or not expiration_timestamp:
                continue
            
            # Calculate days to expiry
            expiry_date = datetime.fromtimestamp(expiration_timestamp / 1000)
            days_left = (expiry_date - datetime.now()).days
            
            # Filter by approximate expiry
            if abs(days_left - days_to_expiry) <= 3:  # Within 3 days of target
                distance_from_atm = abs(strike - current_price)
                
                atm_options.append({
                    "instrument_name": instrument_name,
                    "strike": strike,
                    "days_to_expiry": days_left,
                    "distance_from_atm": distance_from_atm,
                    "option_type": "call" if "-C" in instrument_name else "put"
                })
        
        # Sort by distance from ATM
        atm_options.sort(key=lambda x: x["distance_from_atm"])
        
        # Get the closest ATM options
        atm_calls = [opt for opt in atm_options if opt["option_type"] == "call"][:max_options]
        atm_puts = [opt for opt in atm_options if opt["option_type"] == "put"][:max_options]
        
        result = {
            "currency": currency,
            "current_price": current_price,
            "atm_calls": atm_calls,
            "atm_puts": atm_puts
        }
        
        print(f"✅ Found {len(atm_calls)} ATM calls and {len(atm_puts)} ATM puts")
        
        return result
        
    except Exception as e:
        print(f"❌ Error finding ATM options: {e}")
        return {"error": str(e)}


def demo_options_trading():
    """
    Demonstrate options trading functionality
    """
    print("🚀 Deribit Options Trading Demo")
    print("=" * 60)
    print("⚠️  DEMO MODE - Using testnet environment")
    
    try:
        # 1. Find ATM options
        print(f"\n📊 Step 1: Find ATM BTC options")
        atm_options = find_atm_options("BTC", days_to_expiry=7, env="testnet")
        
        if atm_options.get("error"):
            print(f"❌ Could not find ATM options: {atm_options['error']}")
            return
        
        atm_calls = atm_options.get("atm_calls", [])
        atm_puts = atm_options.get("atm_puts", [])
        
        if not atm_calls and not atm_puts:
            print("❌ No ATM options found")
            return
        
        # 2. Get orderbook for a sample option
        sample_option = None
        if atm_calls:
            sample_option = atm_calls[0]["instrument_name"]
        elif atm_puts:
            sample_option = atm_puts[0]["instrument_name"]
        
        if sample_option:
            print(f"\n📋 Step 2: Get orderbook for {sample_option}")
            orderbook = get_options_orderbook(sample_option, env="testnet")
        
        # 3. Check existing positions and orders
        print(f"\n📊 Step 3: Check existing positions and orders")
        positions = get_options_positions("BTC", "testnet")
        orders = get_open_options_orders("BTC", "testnet")
        
        # 4. Demo order placement (commented for safety)
        print(f"\n📝 Step 4: Demo order placement")
        print("⚠️  Order placement is commented out for safety")
        print("Uncomment the code below to place actual orders:")
        
        if sample_option and orderbook:
            best_bid = orderbook.get("best_bid", 0)
            best_ask = orderbook.get("best_ask", 0)
            
            if best_bid > 0 and best_ask > 0:
                limit_price = best_bid + 0.001  # Slightly above bid
                
                print(f"""
# Example 1: Options Market Buy Order
market_result = place_options_market_order(
    instrument="{sample_option}",
    side="buy",
    amount=1  # 1 contract
)

# Example 2: Options Limit Sell Order
limit_result = place_options_limit_order(
    instrument="{sample_option}",
    side="sell", 
    amount=1,
    price={limit_price:.4f}  # {limit_price:.4f}
)

# Example 3: Smart Options Limit Order
smart_result = place_options_limit_order_relative_to_market(
    instrument="{sample_option}",
    side="buy",
    amount=1,
    offset=0.001  # 0.001 above best bid
)

# Example 4: Check Order Status
if limit_result.get('success'):
    order_status = get_options_order_status(limit_result['order_id'])

# Example 5: Cancel Order
if limit_result.get('success'):
    cancel_result = cancel_options_order(limit_result['order_id'])
""")
        
        print(f"\n✅ Demo completed!")
        print(f"💡 Found {len(atm_calls)} ATM calls and {len(atm_puts)} ATM puts")
        print(f"📋 Existing positions: {len(positions)}")
        print(f"📝 Open orders: {len(orders)}")
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    demo_options_trading()
