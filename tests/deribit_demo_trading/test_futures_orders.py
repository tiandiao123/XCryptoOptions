#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple Deribit Order Test
Test basic order placement and cancellation
"""

import sys
import os
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# /home/ubuntu/options_trading/qtrade/order_api/deribit_order_placer/futures_order.py
from qtrade.order_api.deribit_order_placer.futures_order import (
    place_limit_order,
    cancel_order,
    get_order_status,
    get_current_price
)


def test_simple_limit_order():
    """Test a simple limit order placement and cancellation"""
    print("🚀 Simple Deribit Order Test")
    print("=" * 50)
    
    instrument = "BTC-PERPETUAL"
    
    # Get current price
    price_data = get_current_price(instrument, "testnet")
    if not price_data:
        print("❌ Cannot get price data")
        return
    
    current_price = price_data.get("mark_price", 0)
    print(f"💰 Current BTC price: ${current_price:,.2f}")
    
    # Place a limit order well below market (won't fill)
    limit_price = 108000  # Fixed price like in working example
    
    print(f"\n📝 Placing limit buy order...")
    print(f"   Limit price: ${limit_price:,.2f}")
    print(f"   Amount: 10 contracts")
    
    # Place order WITHOUT post_only to avoid issues
    order_result = place_limit_order(
        instrument=instrument,
        side="buy",
        amount=120,
        price=limit_price,
        post_only=False,  # Don't use post_only
        reduce_only=False,
        env="testnet"
    )
    
    if not order_result.get("success"):
        print(f"❌ Order failed: {order_result.get('error')}")
        return
    
    order_id = order_result.get("order_id")
    print(f"✅ Order placed successfully!")
    print(f"   Order ID: {order_id}")
    
    # Wait a moment
    time.sleep(120)
    
    # Check order status
    print(f"\n🔍 Checking order status...")
    status = get_order_status(order_id, "testnet")
    
    if status:
        print(f"   State: {status.get('order_state')}")
        print(f"   Filled: {status.get('filled_amount', 0)}")
    
    # Cancel the order
    print(f"\n🚫 Canceling order...")
    cancel_result = cancel_order(order_id, "testnet")
    
    if cancel_result.get("success"):
        print(f"✅ Order canceled successfully!")
    else:
        print(f"❌ Cancel failed: {cancel_result.get('error')}")
    
    # Final status check
    time.sleep(1)
    print(f"\n🔍 Final status check...")
    final_status = get_order_status(order_id, "testnet")
    
    if final_status:
        print(f"   Final state: {final_status.get('order_state')}")
    
    return {
        "order_result": order_result,
        "cancel_result": cancel_result,
        "final_status": final_status
    }


if __name__ == "__main__":
    test_simple_limit_order()
