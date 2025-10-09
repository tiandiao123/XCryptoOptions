import requests
from typing import Literal, Dict, Any

DERIBIT_BASE = {
    "testnet": "https://test.deribit.com",
    "mainnet": "https://www.deribit.com",
}

Instrument = Literal["BTC-PERPETUAL", "ETH-PERPETUAL"]
Env = Literal["testnet", "mainnet"]

class DeribitAPIError(Exception):
    pass

def get_index_price(currency: str, env: Env = "testnet") -> float:
    """
    获取指定币种的指数价格
    
    Args:
        currency: "BTC" or "ETH"
        env: "testnet" or "mainnet"
    
    Returns:
        Index price as float
    """
    try:
        base = DERIBIT_BASE[env]
        url = f"{base}/api/v2/public/get_index_price"
        
        params = {"index_name": f"{currency.lower()}_usd"}
        
        resp = requests.get(url, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        
        if "result" in data and "index_price" in data["result"]:
            return float(data["result"]["index_price"])
        else:
            raise DeribitAPIError(f"Invalid response format: {data}")
            
    except Exception as e:
        print(f"❌ Error getting index price for {currency}: {e}")
        return 0.0


def get_inverse_perp_usd_price(
    instrument: Instrument,
    env: Env = "testnet",
    timeout: float = 10.0
) -> Dict[str, Any]:
    """
    Fetch current USD-quoted market prices for Deribit inverse-perpetual (BTC/ETH).
    
    Returns dict with: instrument, mark_price, index_price, best_bid, best_ask, mid_price, last_price, timestamp.
    """
    base = DERIBIT_BASE[env]
    url = f"{base}/api/v2/public/ticker"
    resp = requests.get(url, params={"instrument_name": instrument}, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    if data.get("error"):
        raise DeribitAPIError(data["error"])

    result = data.get("result") or {}
    best_bid = result.get("best_bid_price")
    best_ask = result.get("best_ask_price")
    mid_price = None
    if best_bid is not None and best_ask is not None:
        mid_price = (best_bid + best_ask) / 2.0

    return {
        "instrument": instrument,
        # USD-quoted prices on Deribit (inverse contracts settle in coin, quote in USD)
        "mark_price": result.get("mark_price"),
        "index_price": result.get("index_price"),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid_price": mid_price,
        "last_price": result.get("last_price"),
        "timestamp": result.get("timestamp"),
        "env": env,
    }

# ---- quick demo ----
if __name__ == "__main__":
    print(get_inverse_perp_usd_price("BTC-PERPETUAL", env="testnet"))
    print(get_inverse_perp_usd_price("ETH-PERPETUAL", env="testnet"))
