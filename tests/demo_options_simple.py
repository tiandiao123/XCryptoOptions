#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple Options API Demo
Quick demonstration of key options functionality
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qtrade.demo_trade.order_placer.options_contract import get_all_options_instruments, get_options_summary
from qtrade.demo_trade.order_placer.current_options import get_option_greeks, get_atm_options_chain
from qtrade.demo_trade.order_placer.options_orderbook import find_best_options_to_trade

def demo_options_quick():
    """Quick options demo"""
    print("🚀 Quick Options API Demo\n")
    
    # 1. Get all BTC options
    print("📊 Getting all BTC options...")
    btc_options = get_all_options_instruments(uly="BTC-USD")
    print(f"✅ Found {len(btc_options)} BTC options contracts\n")
    
    # 2. Get market summary
    print("📈 Getting market summary...")
    summary = get_options_summary("BTC-USD")
    print(f"✅ Total contracts: {summary['total_contracts']}")
    print(f"✅ Call options: {summary['call_contracts']}")
    print(f"✅ Put options: {summary['put_contracts']}")
    print(f"✅ Strike range: ${summary['strike_range']['min']:,.0f} - ${summary['strike_range']['max']:,.0f}\n")
    
    # 3. Get ATM options
    print("🎯 Getting ATM options chain...")
    atm_chain = get_atm_options_chain("BTC-USD")
    if atm_chain:
        print(f"✅ Spot price: ${atm_chain['spot_price']:,.2f}")
        print(f"✅ ATM calls: {len(atm_chain.get('atm_calls', []))}")
        print(f"✅ ATM puts: {len(atm_chain.get('atm_puts', []))}\n")
    
    # 4. Find best options to trade
    print("🏆 Finding best options to trade...")
    best_options = find_best_options_to_trade("BTC-USD", max_spread_pct=3.0)
    
    if best_options:
        print(f"✅ Found {len(best_options)} liquid options")
        print("🥇 Top 3 recommendations:")
        for i, option in enumerate(best_options[:3]):
            print(f"  {i+1}. {option['instId']}")
            print(f"     Liquidity Score: {option['liquidity_score']:.2f}")
            print(f"     Spread: {option['spread_pct']:.2f}%")
            print(f"     Mid Price: ${option['mid_price']:.4f}")
    
    print("\n🎉 Demo completed!")

if __name__ == "__main__":
    demo_options_quick()
