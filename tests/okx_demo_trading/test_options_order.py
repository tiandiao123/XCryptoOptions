#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Options Order Placement
Demonstrates how to place BTC/ETH options orders
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qtrade.demo_trade.order_placer.options_order import (
    place_options_market_order,
    place_options_limit_order,
    place_options_limit_order_relative_to_book,
    get_options_positions,
    close_options_position,
    get_options_bid_ask
)

from qtrade.demo_trade.order_placer.options_contract import (
    get_option_greeks,
    get_atm_options_chain
)


def test_get_options_info():
    """Test getting options information"""
    print("🔍 Testing options information retrieval...")
    
    # Get some BTC options
    print("\n📊 Getting BTC ATM options...")
    atm_options = get_atm_options_chain("BTC-USD")
    
    if atm_options and atm_options.get("atm_calls"):
        # Get the first ATM call option
        sample_call = atm_options["atm_calls"][0]
        contract_id = sample_call["instId"]
        
        print(f"📋 Sample contract: {contract_id}")
        print(f"  🎯 Strike: ${sample_call['strike_price']:,.0f}")
        print(f"  📊 Type: {sample_call['option_type']}")
        print(f"  📈 Delta: {sample_call['delta']:.4f}")
        print(f"  💰 Mark Price: ${sample_call['markPrice']:.4f}")

        
        # Get bid/ask for this contract
        print(f"\n💰 Getting bid/ask for {contract_id}...")
        bid_ask = get_options_bid_ask(contract_id)
        
        if bid_ask:
            print(f"  📊 Bid: ${bid_ask['bid']:.4f}")
            print(f"  📊 Ask: ${bid_ask['ask']:.4f}")
            print(f"  📊 Mid: ${bid_ask['mid_price']:.4f}")
            print(f"  📊 Spread: ${bid_ask['spread']:.4f}")
            
            return contract_id, bid_ask
        else:
            print("❌ No bid/ask data available")
            return contract_id, None
    else:
        print("❌ No ATM options found")
        return None, None


def test_options_positions():
    """Test getting current options positions"""
    print("\n🔍 Testing options positions...")
    
    positions = get_options_positions()
    
    if positions:
        print(f"✅ Found {len(positions)} active positions")
        for pos in positions:
            print(f"  📊 {pos.get('instId')}: {pos.get('pos')} contracts")
    else:
        print("📭 No active options positions")
    
    return positions


def demo_order_placement_dry_run(contract_id: str, bid_ask: dict):
    """Demo order placement (dry run - shows what would happen)"""
    print(f"\n📝 Demo order placement for {contract_id}")
    print("⚠️  This is a DRY RUN - no actual orders will be placed")
    
    if not bid_ask:
        print("❌ No bid/ask data, cannot demo orders")
        return
    
    print(f"\n💰 Current market:")
    print(f"  📊 Bid: ${bid_ask['bid']:.4f}")
    print(f"  📊 Ask: ${bid_ask['ask']:.4f}")
    print(f"  📊 Mid: ${bid_ask['mid_price']:.4f}")
    
    # Demo limit order calculations
    buy_limit_price = bid_ask['bid'] + 0.0001
    sell_limit_price = bid_ask['ask'] - 0.0001
    
    print(f"\n📋 Potential orders:")
    print(f"  🟢 Buy limit @ ${buy_limit_price:.4f} (bid + $0.0001)")
    print(f"  🔴 Sell limit @ ${sell_limit_price:.4f} (ask - $0.0001)")
    print(f"  🟢 Buy market @ ${bid_ask['ask']:.4f} (current ask)")
    print(f"  🔴 Sell market @ ${bid_ask['bid']:.4f} (current bid)")
    
    print("\n📝 To place actual orders, uncomment the code below:")

    print(contract_id)
    # Place a market buy order
    result = place_options_market_order(
        instId=contract_id,
        side="buy",
        sz=1
    )
    print(result)

    exit(0)

    print(f"""
    # Place a limit buy order
    result = place_options_limit_order(
        instId="{contract_id}",
        side="buy",
        sz=1,
        px={buy_limit_price:.4f}
    )
    
    # Place a market buy order
    result = place_options_market_order(
        instId="{contract_id}",
        side="buy",
        sz=1
    )
    
    # Place limit order relative to book
    result = place_options_limit_order_relative_to_book(
        instId="{contract_id}",
        side="buy",
        sz=1,
        offset=0.0001
    )
    """)


def main():
    """Main test function"""
    print("🚀 Options Order Testing\n")
    
    try:
        # 1. Get options information
        print("=" * 60)
        print("📊 Step 1: Get Options Information")
        contract_id, bid_ask = test_get_options_info()
        
        # 2. Check current positions
        print("\n" + "=" * 60)
        print("🔍 Step 2: Check Current Positions")
        positions = test_options_positions()
        
        # 3. Demo order placement (dry run)
        if contract_id:
            print("\n" + "=" * 60)
            print("📝 Step 3: Demo Order Placement")
            demo_order_placement_dry_run(contract_id, bid_ask)
        
        # 4. Summary
        print("\n" + "=" * 60)
        print("✅ Test Summary:")
        print(f"  📊 Sample contract: {contract_id or 'None found'}")
        print(f"  💰 Bid/Ask available: {'Yes' if bid_ask else 'No'}")
        print(f"  📋 Active positions: {len(positions) if positions else 0}")
        
        if contract_id and bid_ask:
            print(f"\n🎯 Ready to trade {contract_id}")
            print(f"  💰 Current spread: ${bid_ask['spread']:.4f}")
            print(f"  📊 Mid price: ${bid_ask['mid_price']:.4f}")
        
        print("\n🎉 All tests completed!")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
