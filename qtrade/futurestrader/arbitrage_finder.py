import requests
import time
from typing import List, Dict, Tuple

# Binance endpoints
BN_FUTU_BASE = "https://fapi.binance.com"

# OKX helpers
OKX_BASE = "https://www.okx.com"

# BYBIT endpoints
BYBIT_BASE = "https://api.bybit.com"


def bn_get_all_usdtm_last_prices() -> Dict[str, float]:
    r = requests.get(f"{BN_FUTU_BASE}/fapi/v1/ticker/price", timeout=20)
    r.raise_for_status()
    data = r.json()
    return {it["symbol"]: float(it["price"]) for it in data if it["symbol"].endswith("USDT")}


def bn_get_all_usdtm_funding() -> Dict[str, dict]:
    r = requests.get(f"{BN_FUTU_BASE}/fapi/v1/premiumIndex", timeout=20)
    r.raise_for_status()
    data = r.json()
    res = {}
    for it in data:
        sym = it.get("symbol")
        if not sym:
            continue
        last_rate = it.get("lastFundingRate")
        res[sym] = {"funding_rate": float(last_rate) if last_rate is not None else None}
    return res


def okx_get_swap_last_prices() -> Dict[str, float]:
    r = requests.get(f"{OKX_BASE}/api/v5/market/tickers", params={"instType": "SWAP"}, timeout=20)
    r.raise_for_status()
    tickers = r.json().get("data", [])
    res = {}
    for t in tickers:
        inst_id = t.get("instId")
        last = t.get("last")
        if inst_id and last is not None:
            res[inst_id] = float(last)
    return res


def okx_get_funding_rates(inst_ids: List[str]) -> Dict[str, dict]:
    res = {}
    for inst in inst_ids:
        r = requests.get(f"{OKX_BASE}/api/v5/public/funding-rate", params={"instId": inst}, timeout=20)
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            continue
        it = data[0]
        rate = it.get("fundingRate")
        res[inst] = {"funding_rate": float(rate) if rate is not None else None}
    return res


def map_bn_to_okx_inst(symbol: str) -> str:
    # BTCUSDT -> BTC-USDT-SWAP ; handle 1000- prefix
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    if base.startswith("1000"):
        base = base[4:]
    return f"{base}-USDT-SWAP"


def _normalize_bn_price(symbol: str, price: float) -> Tuple[float, bool]:
    # Normalize 1000- prefixed contracts to base units (divide by 1000)
    if symbol.startswith("1000"):
        return price / 1000.0, True
    return price, False


# Bybit helpers
def bybit_get_linear_prices_and_funding() -> Tuple[Dict[str, float], Dict[str, dict]]:
    # Pull last price and fundingRate from tickers
    r = requests.get(f"{BYBIT_BASE}/v5/market/tickers", params={"category": "linear"}, timeout=20)
    r.raise_for_status()
    data = r.json().get("result", {}).get("list", [])
    price_map: Dict[str, float] = {}
    fr_map: Dict[str, dict] = {}
    for it in data:
        symbol = it.get("symbol")
        if not symbol or not symbol.endswith("USDT"):
            continue
        last = it.get("lastPrice") or it.get("lastPriceE4")
        fr = it.get("fundingRate")
        try:
            price = float(last) if last is not None else None
        except Exception:
            price = None
        try:
            fr_val = float(fr) if fr is not None else None
        except Exception:
            fr_val = None
        if price is not None:
            price_map[symbol] = price
        fr_map[symbol] = {"funding_rate": fr_val}
    return price_map, fr_map


def compute_pairs():
    timings: Dict[str, float] = {}

    t0 = time.time()
    bn_last = bn_get_all_usdtm_last_prices()
    timings["bn_last_prices_s"] = time.time() - t0

    t0 = time.time()
    bn_funding = bn_get_all_usdtm_funding()
    timings["bn_funding_s"] = time.time() - t0

    t0 = time.time()
    okx_last = okx_get_swap_last_prices()
    timings["okx_last_prices_s"] = time.time() - t0

    t0 = time.time()
    okx_funding = okx_get_funding_rates(list(okx_last.keys()))
    timings["okx_funding_s"] = time.time() - t0

    t0 = time.time()
    bybit_last, bybit_funding = bybit_get_linear_prices_and_funding()
    timings["bybit_last_prices_and_funding_s"] = time.time() - t0

    rows = []
    for bn_symbol, bn_price in bn_last.items():
        okx_inst = map_bn_to_okx_inst(bn_symbol)
        okx_price = okx_last.get(okx_inst)
        if okx_price is None:
            continue
        bn_price_norm, adjusted = _normalize_bn_price(bn_symbol, bn_price)
        denom = (bn_price_norm + okx_price) / 2.0 if (bn_price_norm + okx_price) != 0 else 1.0
        spread_pct = abs(bn_price_norm - okx_price) / denom
        rows.append({
            "bn_symbol": bn_symbol,
            "okx_inst": okx_inst,
            "bn_price": bn_price_norm,
            "bn_price_raw": bn_price,
            "bn_adjusted": adjusted,
            "okx_price": okx_price,
            "spread_pct": spread_pct,
            "bn_fr": (bn_funding.get(bn_symbol) or {}).get("funding_rate"),
            "okx_fr": (okx_funding.get(okx_inst) or {}).get("funding_rate"),
            "pair": "BN-OKX",
        })

    # BN vs Bybit
    for bn_symbol, bn_price in bn_last.items():
        byb_price = bybit_last.get(bn_symbol)
        if byb_price is None:
            # if one side has 1000- and the other is base, try adjust symbol
            base = bn_symbol[:-4] if bn_symbol.endswith("USDT") else bn_symbol
            if base.startswith("1000"):
                alt = f"{base[4:]}USDT"
                byb_price = bybit_last.get(alt)
                byb_symbol = alt if byb_price is not None else bn_symbol
            else:
                byb_symbol = bn_symbol
        else:
            byb_symbol = bn_symbol

        if byb_price is None:
            continue

        # Normalize if exactly one side is 1000-
        bn_is_1000 = bn_symbol.startswith("1000")
        byb_is_1000 = byb_symbol.startswith("1000")
        bn_norm = bn_price
        byb_norm = byb_price
        adjusted_flag = False
        if bn_is_1000 and not byb_is_1000:
            bn_norm = bn_price / 1000.0
            adjusted_flag = True
        elif byb_is_1000 and not bn_is_1000:
            byb_norm = byb_price / 1000.0
            adjusted_flag = True

        denom = (bn_norm + byb_norm) / 2.0 if (bn_norm + byb_norm) != 0 else 1.0
        spread_pct = abs(bn_norm - byb_norm) / denom
        rows.append({
            "bn_symbol": bn_symbol,
            "okx_inst": byb_symbol,  # reuse key name to keep printer simple
            "bn_price": bn_norm,
            "bn_price_raw": bn_price,
            "bn_adjusted": adjusted_flag,
            "okx_price": byb_norm,
            "spread_pct": spread_pct,
            "bn_fr": (bn_funding.get(bn_symbol) or {}).get("funding_rate"),
            "okx_fr": (bybit_funding.get(byb_symbol) or {}).get("funding_rate"),
            "pair": "BN-BYBIT",
        })

    # OKX vs Bybit
    for okx_inst, okx_price in okx_last.items():
        base = okx_inst.split("-")[0]
        byb_symbol = f"{base}USDT"
        byb_price = bybit_last.get(byb_symbol)
        if byb_price is None:
            # try 1000-
            byb_symbol_alt = f"1000{base}USDT"
            byb_price = bybit_last.get(byb_symbol_alt)
            byb_symbol = byb_symbol_alt if byb_price is not None else byb_symbol
        if byb_price is None:
            continue

        # Normalize if Bybit side is 1000-
        byb_norm = byb_price / 1000.0 if byb_symbol.startswith("1000") else byb_price
        denom = (okx_price + byb_norm) / 2.0 if (okx_price + byb_norm) != 0 else 1.0
        spread_pct = abs(okx_price - byb_norm) / denom
        rows.append({
            "bn_symbol": okx_inst,    # reuse keys for printer
            "okx_inst": byb_symbol,
            "bn_price": okx_price,
            "bn_price_raw": okx_price,
            "bn_adjusted": byb_symbol.startswith("1000"),
            "okx_price": byb_norm,
            "spread_pct": spread_pct,
            "bn_fr": (okx_funding.get(okx_inst) or {}).get("funding_rate"),
            "okx_fr": (bybit_funding.get(byb_symbol) or {}).get("funding_rate"),
            "pair": "OKX-BYBIT",
        })

    return rows, timings


if __name__ == "__main__":
    pairs_all, timings = compute_pairs()

    # 1) 按价差比例排序
    pairs_spread = sorted(pairs_all, key=lambda x: x["spread_pct"], reverse=True)[:40]
    print("\n🔍 永续 价差 Top（按价差比例，含 BN-OKX / BN-BYBIT / OKX-BYBIT）：")

    def lr_labels(pair: str):
        if pair == "BN-OKX":
            return "BN", "OKX"
        if pair == "BN-BYBIT":
            return "BN", "BYBIT"
        if pair == "OKX-BYBIT":
            return "OKX", "BYBIT"
        return "L", "R"

    for it in pairs_spread:
        bn_fr = it['bn_fr']
        okx_fr = it['okx_fr']
        bn_fr_str = f"{bn_fr:.8f}" if isinstance(bn_fr, float) else "NA"
        okx_fr_str = f"{okx_fr:.8f}" if isinstance(okx_fr, float) else "NA"
        l, r = lr_labels(it['pair'])
        print(
            f"[{it['pair']}] {it['bn_symbol']:12s} <-> {it['okx_inst']:16s} | "
            f"{l}: {it['bn_price']:.6f}{'*' if it['bn_adjusted'] else ' '} | {r}: {it['okx_price']:.6f} | "
            f"Spread: {it['spread_pct']*100:6.3f}% | "
            f"FR({l}): {bn_fr_str:>9} | FR({r}): {okx_fr_str:>9}"
        )

    # 2) 按资金费率差排序（两边 funding rate 绝对差）
    pairs_fr = [p for p in pairs_all if isinstance(p.get('bn_fr'), float) and isinstance(p.get('okx_fr'), float)]
    for p in pairs_fr:
        p["fr_diff_abs"] = abs(p["bn_fr"] - p["okx_fr"])
    pairs_fr_sorted = sorted(pairs_fr, key=lambda x: x["fr_diff_abs"], reverse=True)[:40]
    print("\n🔍 永续 资金费率差 Top（按 |ΔFR|，含 BN-OKX / BN-BYBIT / OKX-BYBIT）：")
    for it in pairs_fr_sorted:
        l, r = lr_labels(it['pair'])
        print(
            f"[{it['pair']}] {it['bn_symbol']:12s} <-> {it['okx_inst']:16s} | "
            f"{l}: {it['bn_price']:.6f}{'*' if it['bn_adjusted'] else ' '} | {r}: {it['okx_price']:.6f} | "
            f"FR({l}): {it['bn_fr']:.8f} | FR({r}): {it['okx_fr']:.8f} | "
            f"|ΔFR|: {it['fr_diff_abs']:.8f}"
        )

    # Benchmarks
    print("\n⏱️  Fetch timings (seconds):")
    for k, v in timings.items():
        print(f"- {k}: {v:.3f}s")


