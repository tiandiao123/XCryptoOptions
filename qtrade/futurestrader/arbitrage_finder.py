import requests
import time
from typing import List, Dict, Tuple
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        # also capture markPrice, nextFundingTime and server time (if present)
        mk = it.get("markPrice")
        next_ft = it.get("nextFundingTime")
        t = it.get("time")
        try:
            mkv = float(mk) if mk is not None else None
        except Exception:
            mkv = None
        try:
            ts = int(t) if t is not None else None
        except Exception:
            ts = None
        try:
            next_ms = int(next_ft) if next_ft is not None else None
        except Exception:
            next_ms = None
        res[sym] = {
            "funding_rate": float(last_rate) if last_rate is not None else None,
            "mark_price": mkv,
            "ts": ts,
            "next_time": next_ms,
        }
    return res


def bn_get_mark_price_map_from_funding() -> Dict[str, Tuple[float, int]]:
    # reuse premiumIndex as mark source
    mp: Dict[str, Tuple[float, int]] = {}
    data = bn_get_all_usdtm_funding()
    for sym, v in data.items():
        if not sym.endswith("USDT"):
            continue
        price = v.get("mark_price")
        ts = v.get("ts")
        if isinstance(price, float):
            mp[sym] = (price, ts if isinstance(ts, int) else None)
    return mp


def okx_get_swap_last_prices() -> Dict[str, float]:
    r = requests.get(f"{OKX_BASE}/api/v5/market/tickers", params={"instType": "SWAP"}, timeout=20)
    r.raise_for_status()
    tickers = r.json().get("data", [])
    res = {}
    for t in tickers:
        inst_id = t.get("instId")
        last = t.get("last")
        if inst_id and last is not None and inst_id.endswith("-USDT-SWAP"):
            res[inst_id] = float(last)
    return res


def okx_get_swap_mark_prices() -> Dict[str, Tuple[float, int]]:
    # mark price for all SWAP; filter USDT-margined
    r = requests.get(f"{OKX_BASE}/api/v5/public/mark-price", params={"instType": "SWAP"}, timeout=20)
    r.raise_for_status()
    data = r.json().get("data", [])
    res: Dict[str, Tuple[float, int]] = {}
    for it in data:
        inst = it.get("instId")
        px = it.get("markPx")
        ts = it.get("ts")
        if not inst or not inst.endswith("-USDT-SWAP"):
            continue
        try:
            res[inst] = (float(px), int(ts) if ts is not None else None)
        except Exception:
            continue
    return res


def okx_get_funding_rates(inst_ids: List[str]) -> Dict[str, dict]:
    # Parallel per instId for speed
    unique = list(dict.fromkeys(inst_ids or []))
    if not unique:
        return {}
    results: Dict[str, dict] = {}

    def fetch(inst: str) -> Tuple[str, dict]:
        try:
            r = requests.get(f"{OKX_BASE}/api/v5/public/funding-rate", params={"instId": inst}, timeout=10)
            r.raise_for_status()
            data = r.json().get("data", [])
            if not data:
                return inst, {"funding_rate": None}
            it = data[0]
            fr = it.get("fundingRate")
            nxt = it.get("nextFundingTime")
            try:
                frv = float(fr) if fr is not None else None
            except Exception:
                frv = None
            try:
                nxt_ms = int(nxt) if nxt is not None else None
            except Exception:
                nxt_ms = None
            return inst, {"funding_rate": frv, "next_time": nxt_ms}
        except Exception:
            return inst, {"funding_rate": None, "next_time": None}

    with ThreadPoolExecutor(max_workers=24) as pool:
        for fut in as_completed([pool.submit(fetch, inst) for inst in unique]):
            inst, val = fut.result()
            results[inst] = val
    return results


def map_bn_to_okx_inst(symbol: str) -> str:
    # BTCUSDT -> BTC-USDT-SWAP ; handle 1000- prefix
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    return f"{base}-USDT-SWAP"


def map_okx_to_bn_symbol(inst_id: str) -> str:
    # e.g., 1000SHIB-USDT-SWAP -> 1000SHIBUSDT
    base = inst_id.split("-")[0]
    return f"{base}USDT"


def map_bybit_to_okx_inst(symbol: str) -> str:
    # e.g., SHIBUSDT or 1000SHIBUSDT -> SHIB-USDT-SWAP or 1000SHIB-USDT-SWAP
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
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
        last = it.get("markPrice") or it.get("lastPrice") or it.get("lastPriceE4")
        fr = it.get("fundingRate")
        ts = it.get("updatedTime") or it.get("ts")
        nxt = it.get("nextFundingTime")
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
        try:
            ts_val = int(ts) if ts is not None else None
        except Exception:
            ts_val = None
        try:
            nxt_ms = int(nxt) if nxt is not None else None
        except Exception:
            nxt_ms = None
        fr_map[symbol] = {"funding_rate": fr_val, "ts": ts_val, "next_time": nxt_ms}
    return price_map, fr_map


def bybit_get_next_times(symbols: List[str]) -> Dict[str, int]:
    # query instruments-info for nextFundingTime or fundingInterval to derive next
    unique = list(dict.fromkeys([s for s in symbols if s.endswith("USDT")]))
    out: Dict[str, int] = {}
    def fetch(sym: str):
        try:
            r = requests.get(f"{BYBIT_BASE}/v5/market/instruments-info", params={"category": "linear", "symbol": sym}, timeout=10)
            r.raise_for_status()
            items = r.json().get("result", {}).get("list", [])
            if not items:
                return sym, None
            it = items[0]
            nxt = it.get("nextFundingTime")
            if nxt is not None:
                return sym, int(nxt)
            # derive using fundingInterval minutes if available
            interval_min = it.get("fundingInterval")
            now = int(time.time() * 1000)
            if interval_min is not None:
                try:
                    mins = int(interval_min)
                    # round up to next multiple of interval since epoch
                    ms = mins * 60 * 1000
                    next_ms = ((now // ms) + 1) * ms
                    return sym, next_ms
                except Exception:
                    pass
            return sym, None
        except Exception:
            return sym, None
    with ThreadPoolExecutor(max_workers=16) as pool:
        for fut in as_completed([pool.submit(fetch, s) for s in unique]):
            sym, val = fut.result()
            out[sym] = val
    return out


def compute_pairs():
    timings: Dict[str, float] = {}

    t0 = time.time()
    bn_last = bn_get_all_usdtm_last_prices()
    timings["bn_last_prices_s"] = time.time() - t0

    t0 = time.time()
    bn_funding = bn_get_all_usdtm_funding()
    timings["bn_funding_s"] = time.time() - t0

    # derive mark price map from funding (BN)
    bn_mark = {k: v for k, v in bn_get_mark_price_map_from_funding().items()}

    t0 = time.time()
    okx_last = okx_get_swap_last_prices()
    timings["okx_last_prices_s"] = time.time() - t0

    t0 = time.time()
    okx_funding = okx_get_funding_rates(list(okx_last.keys()))
    timings["okx_funding_s"] = time.time() - t0

    # OKX mark prices
    t0 = time.time()
    okx_mark = okx_get_swap_mark_prices()
    timings["okx_mark_prices_s"] = time.time() - t0

    t0 = time.time()
    bybit_last, bybit_funding = bybit_get_linear_prices_and_funding()
    timings["bybit_last_prices_and_funding_s"] = time.time() - t0

    # Bybit next funding approx
    t0 = time.time()
    bybit_next = bybit_get_next_times(list(bybit_last.keys()))
    timings["bybit_next_times_s"] = time.time() - t0

    rows = []
    # Prefer mark price if available
    def pick_bn_price(sym: str) -> float | None:
        if sym in bn_mark and isinstance(bn_mark[sym][0], float):
            return bn_mark[sym][0]
        return bn_last.get(sym)

    def pick_okx_price(inst: str) -> float | None:
        if inst in okx_mark and isinstance(okx_mark[inst][0], float):
            return okx_mark[inst][0]
        return okx_last.get(inst)

    for bn_symbol in bn_last.keys():
        bn_price = pick_bn_price(bn_symbol)
        if bn_price is None:
            continue
        okx_inst = map_bn_to_okx_inst(bn_symbol)
        okx_price = pick_okx_price(okx_inst)
        if okx_price is None:
            continue

        bn_is_1000 = bn_symbol.startswith("1000")
        okx_is_1000 = okx_inst.split("-")[0].startswith("1000")

        bn_price_norm = bn_price
        okx_price_norm = okx_price
        adjusted = False
        if bn_is_1000 and not okx_is_1000:
            bn_price_norm = bn_price / 1000.0
            adjusted = True
        elif okx_is_1000 and not bn_is_1000:
            okx_price_norm = okx_price / 1000.0
            adjusted = True

        denom = (bn_price_norm + okx_price_norm) / 2.0 if (bn_price_norm + okx_price_norm) != 0 else 1.0
        spread_pct = abs(bn_price_norm - okx_price_norm) / denom
        bn_fr = (bn_funding.get(bn_symbol) or {}).get("funding_rate")
        okx_fr = (okx_funding.get(okx_inst) or {}).get("funding_rate")
        # Normalize funding to 8h (default 8h for all)
        def norm8(fr):
            return (fr * (8.0 / 8.0)) if isinstance(fr, float) else None
        rows.append({
            "bn_symbol": bn_symbol,
            "okx_inst": okx_inst,
            "bn_price": bn_price_norm,
            "bn_price_raw": bn_price,
            "bn_adjusted": adjusted,
            "okx_price": okx_price_norm,
            "spread_pct": spread_pct,
            "bn_fr": bn_fr,
            "okx_fr": okx_fr,
            "bn_fr8": norm8(bn_fr),
            "okx_fr8": norm8(okx_fr),
            "bn_next": (bn_funding.get(bn_symbol) or {}).get("next_time"),
            "okx_next": (okx_funding.get(okx_inst) or {}).get("next_time"),
            "pair": "BN-OKX",
        })

    # BN vs Bybit
    for bn_symbol in bn_last.keys():
        bn_price = pick_bn_price(bn_symbol)
        if bn_price is None:
            continue
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
        bn_fr = (bn_funding.get(bn_symbol) or {}).get("funding_rate")
        byb_fr = (bybit_funding.get(byb_symbol) or {}).get("funding_rate")
        def norm8(fr):
            return (fr * (8.0 / 8.0)) if isinstance(fr, float) else None
        rows.append({
            "bn_symbol": bn_symbol,
            "okx_inst": byb_symbol,  # reuse key name to keep printer simple
            "bn_price": bn_norm,
            "bn_price_raw": bn_price,
            "bn_adjusted": adjusted_flag,
            "okx_price": byb_norm,
            "spread_pct": spread_pct,
            "bn_fr": bn_fr,
            "okx_fr": byb_fr,
            "bn_fr8": norm8(bn_fr),
            "okx_fr8": norm8(byb_fr),
            "bn_next": (bn_funding.get(bn_symbol) or {}).get("next_time"),
            "okx_next": bybit_next.get(byb_symbol) or (bybit_funding.get(byb_symbol) or {}).get("next_time"),
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
        okx_fr = (okx_funding.get(okx_inst) or {}).get("funding_rate")
        byb_fr = (bybit_funding.get(byb_symbol) or {}).get("funding_rate")
        def norm8(fr):
            return (fr * (8.0 / 8.0)) if isinstance(fr, float) else None
        rows.append({
            "bn_symbol": okx_inst,    # reuse keys for printer
            "okx_inst": byb_symbol,
            "bn_price": okx_price,
            "bn_price_raw": okx_price,
            "bn_adjusted": byb_symbol.startswith("1000"),
            "okx_price": byb_norm,
            "spread_pct": spread_pct,
            "bn_fr": okx_fr,
            "okx_fr": byb_fr,
            "bn_fr8": norm8(okx_fr),
            "okx_fr8": norm8(byb_fr),
            "bn_next": (okx_funding.get(okx_inst) or {}).get("next_time"),
            "okx_next": bybit_next.get(byb_symbol) or (bybit_funding.get(byb_symbol) or {}).get("next_time"),
            "pair": "OKX-BYBIT",
        })

    return rows, timings

def extract_top_pairs_by_funding_rate_diff(pairs: List[Dict], top_n: int = 40) -> List[Dict]:
    # Filter pairs which have normalized 8h funding on both sides
    valid: List[Dict] = []
    for p in pairs:
        fr_l = p.get("bn_fr8")
        fr_r = p.get("okx_fr8")
        if isinstance(fr_l, float) and isinstance(fr_r, float):
            diff = abs(fr_l - fr_r)
            # compute direction: long lower FR, short higher FR
            if fr_l > fr_r:
                direction = "RIGHT_LONG_LEFT_SHORT"  # long right, short left
            elif fr_l < fr_r:
                direction = "LEFT_LONG_RIGHT_SHORT"
            else:
                direction = "FLAT"
            annual_delta_pct = diff * 3 * 365 * 100.0
            out = dict(p)
            out["fr_diff_abs"] = diff
            out["direction_hint"] = direction
            out["annual_delta_pct"] = annual_delta_pct
            valid.append(out)
    # Sort by abs diff descending and return top_n
    valid.sort(key=lambda x: x["fr_diff_abs"], reverse=True)
    return valid[:top_n]


# ---------- New: Pairwise funding-rate diff helpers ----------

def fetch_bn_fr8_map() -> Dict[str, float]:
    mp = {}
    data = bn_get_all_usdtm_funding()
    for sym, v in data.items():
        fr = v.get("funding_rate")
        if isinstance(fr, float):
            mp[sym] = fr  # assume 8h
    return mp


def fetch_bn_next_map() -> Dict[str, int]:
    nxt = {}
    data = bn_get_all_usdtm_funding()
    for sym, v in data.items():
        t = v.get("next_time") or v.get("ts")
        if isinstance(t, int):
            nxt[sym] = t
    return nxt

def fetch_okx_fr8_map() -> Dict[str, float]:
    last = okx_get_swap_last_prices()
    frs = okx_get_funding_rates(list(last.keys()))
    mp = {}
    for inst, v in frs.items():
        fr = v.get("funding_rate")
        if isinstance(fr, float):
            mp[inst] = fr  # assume 8h
    return mp


def fetch_okx_next_map() -> Dict[str, int]:
    last = okx_get_swap_last_prices()
    frs = okx_get_funding_rates(list(last.keys()))
    nxt = {}
    for inst, v in frs.items():
        t = v.get("next_time")
        if isinstance(t, int):
            nxt[inst] = t
    return nxt

def fetch_bybit_fr8_map() -> Dict[str, float]:
    _, frs = bybit_get_linear_prices_and_funding()
    mp = {}
    for sym, v in frs.items():
        fr = v.get("funding_rate")
        if isinstance(fr, float):
            mp[sym] = fr  # assume 8h
    return mp


def fetch_bybit_next_map() -> Dict[str, int]:
    _, frs = bybit_get_linear_prices_and_funding()
    nxt = {}
    for sym, v in frs.items():
        t = v.get("next_time") or v.get("ts")
        if isinstance(t, int):
            nxt[sym] = t
    return nxt

def _pairwise_fr_topn(
    left_map: Dict[str, float],
    right_map: Dict[str, float],
    left_to_right_mapper,
    pair_label: str,
    top_n: int,
    left_next_map: Dict[str, int] | None = None,
    right_next_map: Dict[str, int] | None = None,
) -> List[Dict]:
    rows: List[Dict] = []
    left_next_map = left_next_map or {}
    right_next_map = right_next_map or {}
    for l_sym, l_fr in left_map.items():
        r_sym = left_to_right_mapper(l_sym)
        r_fr = right_map.get(r_sym)
        if not isinstance(l_fr, float) or not isinstance(r_fr, float):
            continue
        diff = abs(l_fr - r_fr)
        direction = (
            f"LONG RIGHT / SHORT LEFT" if r_fr < l_fr else
            f"LONG LEFT / SHORT RIGHT" if l_fr < r_fr else "FLAT"
        )
        rows.append({
            "pair": pair_label,
            "left_symbol": l_sym,
            "right_symbol": r_sym,
            "left_fr8": l_fr,
            "right_fr8": r_fr,
            "fr_diff_abs": diff,
            "direction_hint": direction,
            "annual_delta_pct": diff * 3 * 365 * 100.0,
            "left_next": left_next_map.get(l_sym),
            "right_next": right_next_map.get(r_sym),
            "left_cd_h": (lambda ms: (f"{max(0, (ms - int(time.time()*1000)) / 3600000):.1f}h") if isinstance(ms, int) else "NA")(left_next_map.get(l_sym)),
            "right_cd_h": (lambda ms: (f"{max(0, (ms - int(time.time()*1000)) / 3600000):.1f}h") if isinstance(ms, int) else "NA")(right_next_map.get(r_sym)),
        })
    rows.sort(key=lambda x: x["fr_diff_abs"], reverse=True)
    return rows[:top_n]


def compare_okx_bybit_topn(top_n: int = 40) -> List[Dict]:
    okx = fetch_okx_fr8_map()
    byb = fetch_bybit_fr8_map()
    okx_next = fetch_okx_next_map()
    byb_next = fetch_bybit_next_map()
    return _pairwise_fr_topn(
        left_map=okx,
        right_map=byb,
        left_to_right_mapper=lambda inst: map_okx_to_bn_symbol(inst),  # OKX base→ BASEUSDT (Bybit uses same)
        pair_label="OKX-BYBIT",
        top_n=top_n,
        left_next_map=okx_next,
        right_next_map=byb_next,
    )


def compare_okx_binance_topn(top_n: int = 40) -> List[Dict]:
    okx = fetch_okx_fr8_map()
    bn = fetch_bn_fr8_map()
    okx_next = fetch_okx_next_map()
    bn_next = fetch_bn_next_map()
    return _pairwise_fr_topn(
        left_map=okx,
        right_map=bn,
        left_to_right_mapper=lambda inst: map_okx_to_bn_symbol(inst),
        pair_label="OKX-BN",
        top_n=top_n,
        left_next_map=okx_next,
        right_next_map=bn_next,
    )


def compare_bybit_binance_topn(top_n: int = 40) -> List[Dict]:
    byb = fetch_bybit_fr8_map()
    bn = fetch_bn_fr8_map()
    byb_next = fetch_bybit_next_map()
    bn_next = fetch_bn_next_map()
    return _pairwise_fr_topn(
        left_map=byb,
        right_map=bn,
        left_to_right_mapper=lambda sym: sym,  # Bybit symbol == BN symbol for USDT perps
        pair_label="BYBIT-BN",
        top_n=top_n,
        left_next_map=byb_next,
        right_next_map=bn_next,
    )


def aggregate_topk_from_three(top_n_each: int = 40, top_k: int = 20) -> List[Dict]:
    a = compare_okx_bybit_topn(top_n_each)
    b = compare_okx_binance_topn(top_n_each)
    c = compare_bybit_binance_topn(top_n_each)
    merged = a + b + c
    merged.sort(key=lambda x: x["fr_diff_abs"], reverse=True)
    return merged[:top_k]


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

    def fmt_countdown(ms_value):
        if not isinstance(ms_value, int):
            return "NA"
        now_ms = int(time.time() * 1000)
        remain = max(0, (ms_value - now_ms) // 1000)
        h = remain // 3600
        m = (remain % 3600) // 60
        s = remain % 60
        eta_utc = datetime.fromtimestamp(ms_value/1000, tz=timezone.utc).strftime('%H:%M:%S')
        return f"{eta_utc} UTC {h:02d}:{m:02d}:{s:02d}"

    for it in pairs_spread:
        bn_fr = it['bn_fr']
        okx_fr = it['okx_fr']
        bn_fr_str = f"{bn_fr:.8f}" if isinstance(bn_fr, float) else "NA"
        okx_fr_str = f"{okx_fr:.8f}" if isinstance(okx_fr, float) else "NA"
        l, r = lr_labels(it['pair'])
        l_cd = fmt_countdown(it.get('bn_next'))
        r_cd = fmt_countdown(it.get('okx_next'))
        print(
            f"[{it['pair']}] {it['bn_symbol']:12s} <-> {it['okx_inst']:16s} | "
            f"{l}: {it['bn_price']:.6f}{'*' if it['bn_adjusted'] else ' '} | {r}: {it['okx_price']:.6f} | "
            f"Spread: {it['spread_pct']*100:6.3f}% | "
            f"FR({l}): {bn_fr_str:>9} | FR({r}): {okx_fr_str:>9} | "
            f"Next({l}): {l_cd} | Next({r}): {r_cd}"
        )

    # 2) 按资金费率差排序（两边 funding rate 绝对差）
    pairs_fr = [p for p in pairs_all if isinstance(p.get('bn_fr8'), float) and isinstance(p.get('okx_fr8'), float)]
    for p in pairs_fr:
        p["fr_diff_abs"] = abs(p["bn_fr8"] - p["okx_fr8"])
    pairs_fr_sorted = sorted(pairs_fr, key=lambda x: x["fr_diff_abs"], reverse=True)[:40]
    print("\n🔍 永续 资金费率差 Top（按 |ΔFR|，含 BN-OKX / BN-BYBIT / OKX-BYBIT）：")
    for it in pairs_fr_sorted:
        l, r = lr_labels(it['pair'])
        # Direction: short higher FR, long lower FR (receive net funding)
        direction = ""
        if isinstance(it.get('bn_fr8'), float) and isinstance(it.get('okx_fr8'), float):
            if it['bn_fr8'] > it['okx_fr8']:
                direction = f"LONG {r} / SHORT {l}"
            elif it['bn_fr8'] < it['okx_fr8']:
                direction = f"LONG {l} / SHORT {r}"
        annual_delta_pct = it['fr_diff_abs'] * 3 * 365 * 100.0 if isinstance(it.get('fr_diff_abs'), float) else None
        bn_fr_val = it.get('bn_fr')
        okx_fr_val = it.get('okx_fr')
        bn_fr_str = f"{bn_fr_val:.8f}" if isinstance(bn_fr_val, float) else "NA"
        okx_fr_str = f"{okx_fr_val:.8f}" if isinstance(okx_fr_val, float) else "NA"
        ann_str = f"{annual_delta_pct:.2f}%" if isinstance(annual_delta_pct, float) else "NA"
        l_cd = fmt_countdown(it.get('bn_next'))
        r_cd = fmt_countdown(it.get('okx_next'))
        print(
            f"[{it['pair']}] {it['bn_symbol']:12s} <-> {it['okx_inst']:16s} | "
            f"{l}: {it['bn_price']:.6f}{'*' if it['bn_adjusted'] else ' '} | {r}: {it['okx_price']:.6f} | "
            f"FR({l}): {bn_fr_str} | FR({r}): {okx_fr_str} | "
            f"|ΔFR|8h: {it['fr_diff_abs']:.8f} | Dir: {direction or 'NA'} | AnnΔ≈ {ann_str} | "
            f"Next({l}): {l_cd} | Next({r}): {r_cd}"
        )

    # Benchmarks
    print("\n⏱️  Fetch timings (seconds):")
    for k, v in timings.items():
        print(f"- {k}: {v:.3f}s")


