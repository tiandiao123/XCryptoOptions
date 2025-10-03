#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Deribit Account Balance Functions
Demonstrates individual balance and position functions
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from qtrade.demo_trade.deribit_order_placer.current_balance import (
    get_account_summary,
    get_all_account_summaries,
    get_positions,
    get_open_orders,
    get_portfolio_summary,
    get_access_token
)


def test_authentication():
    """Test Deribit authentication"""
    print("🔐 Testing Deribit Authentication")
    print("=" * 50)
    
    try:
        token = get_access_token("testnet")
        print(f"✅ Authentication successful!")
        print(f"   Token: {token[:30]}...")
        print(f"   Length: {len(token)} characters")
        return True
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return False


def test_individual_currency_balance():
    """Test getting balance for individual currencies"""
    print("\n💰 Testing Individual Currency Balances")
    print("=" * 50)
    
    # Test BTC balance
    print("📊 BTC Balance:")
    btc_summary = get_account_summary("BTC", "testnet")
    
    print("\n📊 ETH Balance:")
    eth_summary = get_account_summary("ETH", "testnet")
    
    return btc_summary, eth_summary


def test_all_balances():
    """Test getting all account balances at once"""
    print("\n🏦 Testing All Account Balances")
    print("=" * 50)
    
    all_summaries = get_all_account_summaries("testnet")
    
    print(f"\n📋 Summary:")
    for currency, summary in all_summaries.items():
        balance = summary.get('balance', 0)
        equity = summary.get('equity', 0)
        available = summary.get('available_funds', 0)
        
        print(f"   {currency}:")
        print(f"      Balance: {balance:.8f} {currency}")
        print(f"      Equity: {equity:.8f} {currency}")
        print(f"      Available: {available:.8f} {currency}")
    
    return all_summaries


def test_positions_and_orders():
    """Test getting positions and orders"""
    print("\n📊 Testing Positions and Orders")
    print("=" * 50)
    
    # Test all positions
    print("🔍 All Positions:")
    all_positions = get_positions(env="testnet")
    
    # Test BTC positions only
    print("\n🔍 BTC Positions:")
    btc_positions = get_positions(currency="BTC", env="testnet")
    
    # Test options positions only
    print("\n🔍 Options Positions:")
    options_positions = get_positions(kind="option", env="testnet")
    
    # Test open orders
    print("\n📝 Open Orders:")
    open_orders = get_open_orders(env="testnet")
    
    return {
        'all_positions': all_positions,
        'btc_positions': btc_positions,
        'options_positions': options_positions,
        'open_orders': open_orders
    }


def test_complete_portfolio():
    """Test getting complete portfolio summary"""
    print("\n🎯 Testing Complete Portfolio Summary")
    print("=" * 50)
    
    portfolio = get_portfolio_summary("testnet")
    
    print(f"\n📋 Portfolio Analysis:")
    print(f"   Environment: {portfolio['env']}")
    print(f"   Timestamp: {portfolio['timestamp']}")
    print(f"   Total USD Value: ${portfolio['total_usd_value']:.2f}")
    print(f"   Number of Currencies: {len(portfolio['account_summaries'])}")
    print(f"   Active Positions: {len(portfolio['positions'])}")
    print(f"   Open Orders: {len(portfolio['open_orders'])}")
    
    return portfolio


def main():
    """Run all balance tests"""
    print("🚀 Deribit Account Balance Tests")
    print("=" * 60)
    
    results = {}
    
    try:
        # Test 1: Authentication
        auth_success = test_authentication()
        results['authentication'] = auth_success
        
        if not auth_success:
            print("❌ Cannot proceed without authentication")
            return results
        
        # Test 2: Individual currency balances
        btc_summary, eth_summary = test_individual_currency_balance()
        results['btc_summary'] = btc_summary
        results['eth_summary'] = eth_summary
        
        # Test 3: All balances
        all_summaries = test_all_balances()
        results['all_summaries'] = all_summaries
        
        # Test 4: Positions and orders
        positions_orders = test_positions_and_orders()
        results.update(positions_orders)
        
        # Test 5: Complete portfolio
        portfolio = test_complete_portfolio()
        results['portfolio'] = portfolio
        
        # Final summary
        print(f"\n" + "=" * 60)
        print(f"✅ All Tests Completed Successfully!")
        print(f"📊 Test Results:")
        print(f"   🔐 Authentication: {'✅' if results['authentication'] else '❌'}")
        print(f"   💰 BTC Balance: {results['btc_summary'].get('balance', 0):.8f} BTC")
        print(f"   💰 ETH Balance: {results['eth_summary'].get('balance', 0):.8f} ETH")
        print(f"   📋 Total Positions: {len(results['all_positions'])}")
        print(f"   📝 Total Orders: {len(results['open_orders'])}")
        
        print(f"\n🎉 Deribit testnet account is ready for trading!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    
    return results


if __name__ == "__main__":
    main()
