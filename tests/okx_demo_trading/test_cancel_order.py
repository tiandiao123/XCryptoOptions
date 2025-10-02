# -*- coding: utf-8 -*-
"""
Test cancel order functionality
"""
import sys
import os
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qtrade.demo_trade.order_placer.inverse_perpetual_contract import (
    get_pending_orders,
    cancel_order,
    cancel_all_orders,
    place_and_track_order,
    place_limit_order_relative_to_book,
    demo_order_management
)

def test_cancel_functionality():
    """Test the cancel order functionality"""
    print("🧪 Testing Cancel Order Functionality...")
    
    # Step 1: Check current pending orders
    print("\n1️⃣ Checking current pending orders...")
    current_orders = get_pending_orders("SWAP", "BTC-USD-SWAP")
    
    # Step 2: Place a limit order that won't fill immediately
    print("\n2️⃣ Placing a limit order...")
    order_info = place_and_track_order(
        instId="BTC-USD-SWAP",
        side="buy",
        btc_notional=0.1,
        ordType="limit",
        price_offset=-200  # $200 below market - should not fill
    )
    
    if order_info and order_info["success"]:
        order_id = order_info["orderId"]
        print(f"✅ Order placed successfully! Order ID: {order_id}")
        
        # Step 3: Wait a moment and check pending orders
        print("\n3️⃣ Waiting 2 seconds then checking pending orders...")
        time.sleep(2)
        pending_orders = get_pending_orders("SWAP", "BTC-USD-SWAP")
        
        # Step 4: Cancel the specific order
        print(f"\n4️⃣ Canceling order {order_id}...")
        cancel_success = cancel_order(order_id, "BTC-USD-SWAP")
        
        if cancel_success:
            print("✅ Order canceled successfully!")
            
            # Step 5: Verify order is gone
            print("\n5️⃣ Verifying order is canceled...")
            time.sleep(1)
            final_orders = get_pending_orders("SWAP", "BTC-USD-SWAP")
            
        else:
            print("❌ Failed to cancel order")
            
    else:
        print("❌ Failed to place test order")
    
    return order_info

def test_orderbook_based_order():
    """Test placing order based on orderbook bid/ask"""
    print("\n🧪 Testing Orderbook-Based Order...")
    
    # Place buy order $10 below current bid
    order_info = place_limit_order_relative_to_book(
        instId="BTC-USD-SWAP",
        side="buy",
        btc_notional=0.1,
        offset_usd=-10  # $10 below bid
    )
    
    if order_info and order_info["success"]:
        print(f"✅ Orderbook-based order placed! ID: {order_info['orderId']}")
        print(f"   Reference price: ${order_info['reference_price']:,.1f}")
        print(f"   Limit price: ${order_info['limit_price']:,.1f}")
        
        # Cancel it after 2 seconds
        time.sleep(2)
        print(f"\n🚫 Canceling orderbook-based order...")
        cancel_order(order_info['orderId'], order_info['instId'])
        
    return order_info

if __name__ == "__main__":
    print("🚀 Starting Order Cancel Tests...")
    
    # Test 1: Basic cancel functionality
    test_result = test_cancel_functionality()
    
    # Test 2: Orderbook-based orders
    test_result2 = test_orderbook_based_order()
    
    print("\n✅ All cancel tests completed!")
