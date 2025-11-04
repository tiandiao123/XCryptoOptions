#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deribit Account Balance Module
Get account balance and position information from Deribit testnet
"""

import requests
from typing import Literal, Dict, Any, List, Optional
from datetime import datetime

from qtrade.order_api.deribit import DERIBIT_BASE, api_config, real_api_config


DERIBIT_BASE = {
    "testnet": "https://test.deribit.com",
    "mainnet": "https://www.deribit.com",
}

Currency = Literal["BTC", "ETH"]
Env = Literal["testnet", "mainnet"]

class DeribitAPIError(Exception):
    pass


def get_access_token(env: Env = "testnet") -> str:
    """
    Get access token for authenticated API calls
    """
    base = DERIBIT_BASE[env]
    url = f"{base}/api/v2/public/auth"
    
    if env == "mainnet":
        response = requests.get(url, params=real_api_config)
    else:
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


def _authenticated_get(path: str, params: Dict[str, Any] = None, env: Env = "testnet") -> Dict[str, Any]:
    """
    Make authenticated GET request to Deribit API
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
    
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    
    data = response.json()
    
    if data.get("error"):
        raise DeribitAPIError(f"API Error: {data['error']}")
    
    return data.get("result", {})


def get_account_summary(currency: Currency, env: Env = "testnet") -> Dict[str, Any]:
    """
    Get account summary for a specific currency
    
    Args:
        currency: "BTC" or "ETH"
        env: "testnet" or "mainnet"
    
    Returns:
        Dict containing account summary information
    """
    print(f"🔍 Getting {currency} account summary...")
    
    try:
        result = _authenticated_get("private/get_account_summary", 
                                  {"currency": currency}, env)
        
        print(f"✅ {currency} Account Summary:")
        print(f"   💰 Balance: {result.get('balance', 0):.8f} {currency}")
        print(f"   📊 Equity: {result.get('equity', 0):.8f} {currency}")
        print(f"   🔒 Available Funds: {result.get('available_funds', 0):.8f} {currency}")
        print(f"   📈 Unrealized PnL: {result.get('total_pl', 0):.8f} {currency}")
        print(f"   💵 USD Value: ${result.get('equity_usd', 0):.2f}")
        print(f"   📊 Margin Balance: {result.get('margin_balance', 0):.8f} {currency}")
        print(f"   🎯 Initial Margin: {result.get('initial_margin', 0):.8f} {currency}")
        print(f"   ⚠️ Maintenance Margin: {result.get('maintenance_margin', 0):.8f} {currency}")
        
        return result
        
    except Exception as e:
        print(f"❌ Error getting {currency} account summary: {e}")
        return {}


def get_all_account_summaries(env: Env = "testnet") -> Dict[str, Dict[str, Any]]:
    """
    Get account summaries for all currencies (BTC and ETH)
    
    Args:
        env: "testnet" or "mainnet"
    
    Returns:
        Dict with currency as key and account summary as value
    """
    print(f"🚀 Getting all account summaries from {env}...")
    
    summaries = {}
    
    for currency in ["BTC", "ETH"]:
        summary = get_account_summary(currency, env)
        if summary:
            summaries[currency] = summary
    
    return summaries


def get_positions(currency: Currency = None, kind: str = None, env: Env = "testnet") -> List[Dict[str, Any]]:
    """
    Get current positions
    
    Args:
        currency: Filter by currency ("BTC", "ETH", or None for all)
        kind: Filter by instrument kind ("future", "option", or None for all)
        env: "testnet" or "mainnet"
    
    Returns:
        List of position dictionaries
    """
    print(f"📊 Getting positions...")
    
    try:
        params = {}
        if currency:
            params["currency"] = currency
        if kind:
            params["kind"] = kind
        
        result = _authenticated_get("private/get_positions", params, env)
        
        if not result:
            print("📭 No positions found")
            return []
        
        positions = result if isinstance(result, list) else [result]
        
        print(f"✅ Found {len(positions)} positions:")
        
        for i, pos in enumerate(positions):
            instrument = pos.get("instrument_name", "Unknown")
            size = pos.get("size", 0)
            direction = pos.get("direction", "unknown")
            mark_price = pos.get("mark_price", 0)
            unrealized_pnl = pos.get("unrealized_pnl", 0)
            
            print(f"\n   📋 Position {i+1}: {instrument}")
            print(f"      Size: {size}")
            print(f"      Direction: {direction}")
            print(f"      Mark Price: ${mark_price:.2f}")
            print(f"      Unrealized PnL: {unrealized_pnl:.8f}")
        
        return positions
        
    except Exception as e:
        print(f"❌ Error getting positions: {e}")
        return []


def get_open_orders(currency: Currency = None, kind: str = None, env: Env = "testnet") -> List[Dict[str, Any]]:
    """
    Get open orders
    
    Args:
        currency: Filter by currency ("BTC", "ETH", or None for all)
        kind: Filter by instrument kind ("future", "option", or None for all)
        env: "testnet" or "mainnet"
    
    Returns:
        List of open order dictionaries
    """
    print(f"📝 Getting open orders...")
    
    try:
        params = {}
        if currency:
            params["currency"] = currency
        if kind:
            params["kind"] = kind
        
        result = _authenticated_get("private/get_open_orders", params, env)
        
        if not result:
            print("📭 No open orders found")
            return []
        
        orders = result if isinstance(result, list) else [result]
        
        print(f"✅ Found {len(orders)} open orders:")
        
        for i, order in enumerate(orders):
            instrument = order.get("instrument_name", "Unknown")
            order_type = order.get("order_type", "unknown")
            direction = order.get("direction", "unknown")
            amount = order.get("amount", 0)
            price = order.get("price", 0)
            order_state = order.get("order_state", "unknown")
            
            print(f"\n   📋 Order {i+1}: {instrument}")
            print(f"      Type: {order_type}")
            print(f"      Direction: {direction}")
            print(f"      Amount: {amount}")
            print(f"      Price: ${price:.4f}")
            print(f"      State: {order_state}")
        
        return orders
        
    except Exception as e:
        print(f"❌ Error getting open orders: {e}")
        return []


def get_portfolio_summary(env: Env = "testnet") -> Dict[str, Any]:
    """
    Get complete portfolio summary including all currencies, positions, and orders
    
    Args:
        env: "testnet" or "mainnet"
    
    Returns:
        Dict containing complete portfolio information
    """
    print(f"🎯 Getting complete portfolio summary...")
    
    portfolio = {
        "timestamp": datetime.now().isoformat(),
        "env": env,
        "account_summaries": {},
        "positions": [],
        "open_orders": [],
        "total_usd_value": 0
    }
    
    # Get account summaries for all currencies
    summaries = get_all_account_summaries(env)
    portfolio["account_summaries"] = summaries
    
    # Calculate total USD value
    total_usd = 0
    for currency, summary in summaries.items():
        usd_value = summary.get("equity_usd", 0)
        total_usd += usd_value
    
    portfolio["total_usd_value"] = total_usd
    
    # Get all positions
    positions = get_positions(env=env)
    portfolio["positions"] = positions
    
    # Get all open orders
    orders = get_open_orders(env=env)
    portfolio["open_orders"] = orders
    
    # Summary
    print(f"\n" + "=" * 50)
    print(f"📊 Portfolio Summary:")
    print(f"   💵 Total USD Value: ${total_usd:.2f}")
    print(f"   📋 Active Positions: {len(positions)}")
    print(f"   📝 Open Orders: {len(orders)}")
    print(f"   🏦 Currencies: {', '.join(summaries.keys())}")
    
    return portfolio


def demo_account_balance():
    """
    Demonstrate account balance functionality
    """
    print("🚀 Deribit Account Balance Demo")
    print("=" * 60)
    
    try:
        # Test authentication
        print("🔐 Testing authentication...")
        token = get_access_token("testnet")
        print(f"✅ Authentication successful! Token: {token[:20]}...")
        
        # Get complete portfolio
        portfolio = get_portfolio_summary("testnet")
        
        print(f"\n🎉 Demo completed successfully!")
        
        return portfolio
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    demo_account_balance()
