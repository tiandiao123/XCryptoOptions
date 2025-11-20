import requests
from typing import Literal, Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone

DERIBIT_BASE = {
    "testnet": "https://test.deribit.com",
    "mainnet": "https://www.deribit.com",
}

Currency = Literal["BTC", "ETH"]

class DeribitAPIError(Exception):
    pass

def _get(base: str, path: str, params: dict, timeout: float = 10.0) -> dict:
    url = f"{base}/api/v2/{path}"
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    js = r.json()
    if js.get("error"):
        raise DeribitAPIError(js["error"])
    return js["result"]

def get_index_price(currency: Currency, env: str = "testnet") -> float:
    """Preferred: /public/get_index_price with index_name 'btc_usd' / 'eth_usd'.
       Fallback: /public/ticker on PERPETUAL to read index_price field."""
    base = DERIBIT_BASE[env]
    idx = f"{currency.lower()}_usd"   # <-- 正确格式
    try:
        res = _get(base, "public/get_index_price", {"index_name": idx})
        # new-ish shape: {"index_price": x, "estimated_delivery_price": y}
        if isinstance(res, dict) and "index_price" in res:
            return float(res["index_price"])
        # older shape: {"BTC": x, "edp": y} / {"ETH": x, "edp": y}
        key = currency.upper()
        if key in res:
            return float(res[key])
        raise DeribitAPIError(f"Unexpected response shape: {res}")
    except Exception:
        # 回退方案：从 PERPETUAL 的 ticker 里拿 index_price
        ins = f"{currency}-PERPETUAL"
        res = _get(base, "public/ticker", {"instrument_name": ins})
        return float(res["index_price"])

def list_live_options(currency: Currency, env: str = "testnet") -> List[Dict[str, Any]]:
    base = DERIBIT_BASE[env]
    return _get(base, "public/get_instruments",
                {"currency": currency, "kind": "option", "expired": "false"})

def pick_atm_option(currency: Currency, env: str = "testnet",
                    prefer_call: Optional[bool] = None) -> Dict[str, Any]:
    spot = get_index_price(currency, env)
    instruments = list_live_options(currency, env)
    ranked: List[Tuple[float, int, bool, Dict[str, Any]]] = []
    for ins in instruments:
        try:
            strike = float(ins["strike"])
            exp_ts = int(ins["expiration_timestamp"])
            opt_type = ins["option_type"]  # "call"/"put"
            pref = (prefer_call is not None and
                    opt_type == ("call" if prefer_call else "put"))
            ranked.append((abs(strike - spot), exp_ts, pref, ins))
        except Exception:
            continue
    if not ranked:
        raise RuntimeError("No live options.")
    ranked.sort(key=lambda x: (x[0], x[1], not x[2]))
    return {"spot": spot, "instrument": ranked[0][3]}

def get_order_book_l1(instrument_name: str, env: str = "testnet") -> Dict[str, Any]:
    base = DERIBIT_BASE[env]
    ob = _get(base, "public/get_order_book",
              {"instrument_name": instrument_name, "depth": 1})
    bids = ob.get("bids") or []
    asks = ob.get("asks") or []
    best_bid = bids[0][0] if bids else None
    best_ask = asks[0][0] if asks else None
    return {
        "instrument_name": instrument_name,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mark_price": ob.get("mark_price"),
        "index_price": ob.get("index_price"),
        "timestamp": ob.get("timestamp"),
    }

# ---- quick demo ----
if __name__ == "__main__":
    CURRENCY: Currency = "BTC"
    env = "testnet"
    atm = pick_atm_option(CURRENCY, env=env)
    spot = atm["spot"]
    ins = atm["instrument"]
    name = ins["instrument_name"]
    expiry = datetime.fromtimestamp(ins["expiration_timestamp"]/1000, tz=timezone.utc)
    print(f"Spot {CURRENCY}-USD (index): {spot:.2f}")
    print(f"ATM: {name}  strike={ins['strike']}  type={ins['option_type']}  "
          f"expiry={expiry:%Y-%m-%d %H:%M:%S %Z}")
    
    l1 = get_order_book_l1(name, env=env)
    print("L1:", l1)
