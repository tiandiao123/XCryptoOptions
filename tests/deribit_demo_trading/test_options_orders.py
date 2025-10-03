#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Deribit Options Order Functions
Demonstrate the new options order placement functions
"""

import sys
import os
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from qtrade.demo_trade.deribit_order_placer.options_order import (
    get_options_instruments,
    get_options_orderbook,
    place_options_limit_order,
    place_options_limit_order_relative_to_market,
    cancel_options_order,
    get_options_order_status,
    find_atm_options,
    get_options_positions,
    get_open_options_orders
)


def test_get_options_instruments():
    """Test getting available options instruments"""
    print("📊 Test 1: Get Options Instruments")
    print("-" * 50)
    
    instruments = get_options_instruments("BTC", expired=False, env="testnet")
    
    if instruments:
        print(f"✅ Found {len(instruments)} BTC options")
        
        # Show first few instruments
        for i, instrument in enumerate(instruments[:3]):
            name = instrument.get("instrument_name", "Unknown")
            strike = instrument.get("strike", 0)
            expiry = instrument.get("expiration_timestamp", 0)
            print(f"   {i+1}. {name} (Strike: ${strike:,.0f})")
        
        return True, instruments[0]["instrument_name"] if instruments else None
    else:
        print("❌ No options instruments found")
        return False, None


def test_get_options_orderbook(sample_instrument):
    """Test getting options orderbook"""
    print(f"\n📋 Test 2: Get Options Orderbook")
    print("-" * 50)
    
    if not sample_instrument:
        print("❌ No sample instrument available")
        return False
    
    orderbook = get_options_orderbook(sample_instrument, env="testnet")
    
    if orderbook:
        print(f"✅ Got orderbook for {sample_instrument}")
        print(f"   Best Bid: {orderbook.get('best_bid', 0):.4f}")
        print(f"   Best Ask: {orderbook.get('best_ask', 0):.4f}")
        print(f"   Spread: {orderbook.get('spread', 0):.4f}")
        return True
    else:
        print(f"❌ Failed to get orderbook for {sample_instrument}")
        return False


def test_find_atm_options():
    """Test finding ATM options"""
    print(f"\n🎯 Test 3: Find ATM Options")
    print("-" * 50)
    
    atm_result = find_atm_options("BTC", days_to_expiry=7, env="testnet")
    
    if atm_result.get("error"):
        print(f"❌ Error finding ATM options: {atm_result['error']}")
        return False, None
    
    atm_calls = atm_result.get("atm_calls", [])
    atm_puts = atm_result.get("atm_puts", [])
    current_price = atm_result.get("current_price", 0)
    
    print(f"✅ Found ATM options around ${current_price:,.2f}")
    print(f"   ATM Calls: {len(atm_calls)}")
    print(f"   ATM Puts: {len(atm_puts)}")
    
    if atm_calls:
        best_call = atm_calls[0]
        print(f"   Best Call: {best_call['instrument_name']} (Strike: ${best_call['strike']:,.0f})")
        return True, best_call['instrument_name']
    elif atm_puts:
        best_put = atm_puts[0]
        print(f"   Best Put: {best_put['instrument_name']} (Strike: ${best_put['strike']:,.0f})")
        return True, best_put['instrument_name']
    else:
        print("❌ No ATM options found")
        return False, None


def test_options_limit_order(sample_instrument):
    """Test placing and canceling options limit order"""
    print(f"\n📝 Test 4: Options Limit Order")
    print("-" * 50)
    
    if not sample_instrument:
        print("❌ No sample instrument available")
        return False
    
    # Get current orderbook
    orderbook = get_options_orderbook(sample_instrument, env="testnet")
    
    if not orderbook or orderbook.get("best_bid", 0) <= 0:
        print(f"❌ No valid orderbook for {sample_instrument}")
        return False
    
    # Place a limit order well below market (won't fill)
    best_bid = orderbook.get("best_bid", 0)
    limit_price = max(0.001, best_bid * 0.5)  # 50% below bid or minimum 0.001
    
    print(f"📝 Placing limit buy order:")
    print(f"   Instrument: {sample_instrument}")
    print(f"   Amount: 1 contract")
    print(f"   Limit Price: {limit_price:.4f}")
    
    result = place_options_limit_order(
        instrument=sample_instrument,
        side="buy",
        amount=1,
        price=limit_price,
        post_only=True,
        env="testnet"
    )
    
    if result.get("success"):
        order_id = result.get("order_id")
        print(f"✅ Options limit order successful! ID: {order_id}")
        
        # Wait a moment
        time.sleep(10)
        
        # Check order status
        print(f"🔍 Checking order status...")
        status = get_options_order_status(order_id, "testnet")
        
        if status:
            print(f"   State: {status.get('order_state')}")
            print(f"   Filled: {status.get('filled_amount', 0)}")
        
        # Cancel the order
        print(f"🚫 Canceling order...")
        cancel_result = cancel_options_order(order_id, "testnet")
        
        if cancel_result.get("success"):
            print(f"✅ Order canceled successfully!")
            return True
        else:
            print(f"❌ Cancel failed: {cancel_result.get('error')}")
            return False
    else:
        print(f"❌ Options limit order failed: {result.get('error')}")
        return False


def test_options_relative_order(sample_instrument):
    """Test placing options order relative to market"""
    print(f"\n📊 Test 5: Options Relative Limit Order")
    print("-" * 50)
    
    if not sample_instrument:
        print("❌ No sample instrument available")
        return False
    
    print(f"📝 Placing relative limit order:")
    print(f"   Instrument: {sample_instrument}")
    print(f"   Amount: 1 contract")
    print(f"   Offset: 0.001 above best bid")
    
    result = place_options_limit_order_relative_to_market(
        instrument=sample_instrument,
        side="buy",
        amount=1,
        offset=0.001,
        post_only=True,
        env="testnet"
    )
    
    if result.get("success"):
        order_id = result.get("order_id")
        reference_price = result.get("reference_price", 0)
        
        print(f"✅ Options relative order successful! ID: {order_id}")
        print(f"   Reference Price: {reference_price:.4f}")
        
        # Cancel immediately
        time.sleep(10)
        cancel_result = cancel_options_order(order_id, "testnet")
        print(f"🚫 Cancel result: {'✅' if cancel_result.get('success') else '❌'}")
        
        return True
    else:
        print(f"❌ Options relative order failed: {result.get('error')}")
        return False


def test_options_positions_and_orders():
    """Test getting options positions and orders"""
    print(f"\n📊 Test 6: Options Positions and Orders")
    print("-" * 50)
    
    # Get positions
    positions = get_options_positions("BTC", "testnet")
    print(f"📊 Current positions: {len(positions)}")
    
    # Get open orders
    orders = get_open_options_orders("BTC", "testnet")
    print(f"📝 Open orders: {len(orders)}")
    
    return True


def main():
    """Run all options order tests"""
    print("🚀 Deribit Options Order Functions Test")
    print("=" * 70)
    print("Testing the new options order placement functions")
    print("=" * 70)
    
    results = {}
    sample_instrument = None
    atm_instrument = None
    
    # Test 1: Get instruments
    results["instruments"], sample_instrument = test_get_options_instruments()

    
    # Test 2: Get orderbook
    if sample_instrument:
        results["orderbook"] = test_get_options_orderbook(sample_instrument)
    else:
        results["orderbook"] = False
    

    
    # Test 3: Find ATM options
    results["atm_options"], atm_instrument = test_find_atm_options()
    
    # Use ATM instrument if available, otherwise use sample
    test_instrument = atm_instrument or sample_instrument


    
    # Test 4: Limit order
    if test_instrument:
        results["limit_order"] = test_options_limit_order(test_instrument)
    else:
        results["limit_order"] = False
    
    # Test 5: Relative order
    if test_instrument:
        results["relative_order"] = test_options_relative_order(test_instrument)
    else:
        results["relative_order"] = False
    
    exit(0)
    
    # Test 6: Positions and orders
    results["positions_orders"] = test_options_positions_and_orders()
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 Test Results Summary:")
    print("=" * 70)
    print(f"📊 Get Instruments:        {'✅ WORKS' if results['instruments'] else '❌ FAILED'}")
    print(f"📋 Get Orderbook:         {'✅ WORKS' if results['orderbook'] else '❌ FAILED'}")
    print(f"🎯 Find ATM Options:      {'✅ WORKS' if results['atm_options'] else '❌ FAILED'}")
    print(f"📝 Options Limit Order:   {'✅ WORKS' if results['limit_order'] else '❌ FAILED'}")
    print(f"📊 Options Relative Order: {'✅ WORKS' if results['relative_order'] else '❌ FAILED'}")
    print(f"📊 Positions & Orders:    {'✅ WORKS' if results['positions_orders'] else '❌ FAILED'}")
    
    success_count = sum(results.values())
    total_tests = len(results)
    
    print(f"\n🎯 Overall: {success_count}/{total_tests} tests passed")
    
    if success_count == total_tests:
        print("🎉 All options order functions working perfectly!")
        print("💡 You can now trade options on Deribit!")
    else:
        print("⚠️  Some tests failed - check the error messages above")
    
    return results


if __name__ == "__main__":
    main()
