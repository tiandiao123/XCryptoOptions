# -*- coding: utf-8 -*-
"""
Simple orderbook utilities for getting bid-1 and ask-1 prices
"""
import requests
from typing import Dict, Optional, List

OKX_BASE_URL = "https://www.okx.com"

def get_bid_ask(instId: str) -> Optional[Dict]:
    """
    Simple function to get bid-1 and ask-1 prices for a contract
    
    Args:
        instId: Contract ID like "BTC-USD-SWAP", "ETH-USD-SWAP"
        
    Returns:
        dict with keys: bid, ask, mid, spread, spread_pct
        None if failed
    """
    try:
        url = f"{OKX_BASE_URL}/api/v5/market/books"
        params = {"instId": instId, "sz": "1"}
        
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("code") not in ("0", 0, None):
            return None
        
        book_data = data.get("data", [])
        if not book_data:
            return None
        
        book = book_data[0]
        bids = book.get("bids", [])
        asks = book.get("asks", [])
        
        if not bids or not asks:
            return None
        
        bid = float(bids[0][0])
        ask = float(asks[0][0])
        mid = (bid + ask) / 2
        spread = ask - bid
        spread_pct = (spread / bid) * 100
        
        return {
            "instId": instId,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "spread": spread,
            "spread_pct": spread_pct,
            "timestamp": book.get("ts")
        }
        
    except Exception:
        return None

def get_multiple_bid_ask(instIds: List[str]) -> Dict[str, Dict]:
    """
    Get bid-1 and ask-1 for multiple contracts
    
    Args:
        instIds: List of contract IDs
        
    Returns:
        dict mapping instId to bid/ask data
    """
    results = {}
    
    for instId in instIds:
        data = get_bid_ask(instId)
        if data:
            results[instId] = data
    
    return results

def print_bid_ask(instId: str):
    """Print bid-1 and ask-1 in a clean format"""
    data = get_bid_ask(instId)
    if data:
        print(f"{instId}: Bid ${data['bid']:,.1f} | Ask ${data['ask']:,.1f} | Spread ${data['spread']:.1f}")
        return data
    else:
        print(f"{instId}: Failed to get data")
        return None

# Quick access functions
def btc_bid_ask():
    """Get BTC-USD-SWAP bid/ask"""
    return get_bid_ask("BTC-USD-SWAP")

def eth_bid_ask():
    """Get ETH-USD-SWAP bid/ask"""
    return get_bid_ask("ETH-USD-SWAP")

if __name__ == "__main__":
    # Demo usage
    print("=== Simple Orderbook Demo ===")
    
    # Single contract
    btc_data = btc_bid_ask()
    if btc_data:
        print(f"BTC: ${btc_data['bid']:,.1f} / ${btc_data['ask']:,.1f}")
    
    # Multiple contracts
    contracts = ["BTC-USD-SWAP", "ETH-USD-SWAP"]
    all_data = get_multiple_bid_ask(contracts)
    
    print("\nAll Contracts:")
    for instId, data in all_data.items():
        print(f"  {instId}: ${data['bid']:,.1f} / ${data['ask']:,.1f}")
