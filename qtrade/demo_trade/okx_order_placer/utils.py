#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for leverage setup and contract specifications
"""

import requests


def get_instrument_details(instId="BTC-USD-SWAP"):
    """Get contract specifications (no auth needed for public data)"""
    print(f"Getting contract specifications for {instId}...")
    
    try:
        # Public API call - no authentication needed
        url = f"https://www.okx.com/api/v5/public/instruments?instType=SWAP&instId={instId}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("code") == "0" and data.get("data"):
            contract_info = data["data"][0]
            
            print("✅ Contract Details:")
            print(f"  📋 Instrument ID: {contract_info.get('instId')}")
            print(f"  💰 Contract Value: {contract_info.get('ctVal')} {contract_info.get('ctValCcy')}")
            print(f"  📏 Contract Multiplier: {contract_info.get('ctMult')}")
            print(f"  🎯 Contract Type: {contract_info.get('ctType')}")
            print(f"  💱 Base Currency: {contract_info.get('baseCcy')}")
            print(f"  💵 Quote Currency: {contract_info.get('quoteCcy')}")
            print(f"  📈 Settlement Currency: {contract_info.get('settleCcy')}")
            print(f"  🔢 Lot Size: {contract_info.get('lotSz')}")
            print(f"  📊 Min Size: {contract_info.get('minSz')}")
            print(f"  📈 Max Leverage: {contract_info.get('lever')}")
            print(f"  💸 Tick Size: {contract_info.get('tickSz')}")
            
            # Calculate 1 contract in BTC
            ct_val = float(contract_info.get('ctVal', 0))
            print(f"\n🎯 Key Info:")
            print(f"  • 1 Contract = ${ct_val:,.0f} USD notional")
            print(f"  • This is an INVERSE contract - denominated in BTC")
            print(f"  • P&L is calculated in BTC (settlement currency)")
            
            return contract_info
        else:
            print(f"❌ Failed to get contract info: {data}")
            return None
            
    except Exception as e:
        print(f"❌ Error getting contract details: {e}")
        return None


def get_current_btc_price(instId="BTC-USD-SWAP"):
    
    try:
        # Public API call - no authentication needed
        url = f"https://www.okx.com/api/v5/market/ticker?instId={instId}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("code") == "0" and data.get("data"):
            ticker = data["data"][0]
            current_price = float(ticker.get("last", 0))
            return current_price
    except Exception as e:
        print(f"❌ Error getting current BTC price: {e}")
        return None