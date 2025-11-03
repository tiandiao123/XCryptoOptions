import requests
from datetime import datetime, timezone
import csv

SPOT_BASE = "https://api.binance.com"
FUTU_BASE = "https://fapi.binance.com"

def get_all_spot_usdt_prices():
    r = requests.get(f"{SPOT_BASE}/api/v3/ticker/price", timeout=20)
    r.raise_for_status()
    data = r.json()
    return {item["symbol"]: float(item["price"]) 
            for item in data if item["symbol"].endswith("USDT")}

def get_all_usdtm_funding():
    r = requests.get(f"{FUTU_BASE}/fapi/v1/premiumIndex", timeout=20)
    r.raise_for_status()
    data = r.json()
    funding_map = {}
    for it in data:
        sym = it.get("symbol")
        if not sym:
            continue
        last_rate = it.get("lastFundingRate")
        next_time = it.get("nextFundingTime")
        funding_map[sym] = {
            "funding_rate": float(last_rate) if last_rate is not None else None,
            "next_funding_time": int(next_time) if next_time is not None else None,
        }
    return funding_map

def get_all_usdtm_last_prices():
    r = requests.get(f"{FUTU_BASE}/fapi/v1/ticker/price", timeout=20)
    r.raise_for_status()
    data = r.json()
    return {item["symbol"]: float(item["price"]) 
            for item in data if item["symbol"].endswith("USDT")}

def ms_to_utc_iso(ms):
    if ms is None:
        return ""
    return datetime.fromtimestamp(ms/1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")

def build_table():
    spot = get_all_spot_usdt_prices()
    funding = get_all_usdtm_funding()
    futu_last = get_all_usdtm_last_prices()
    rows = []
    for sym, price in spot.items():
        f = funding.get(sym)
        rate = f["funding_rate"] if f else None
        next_ts = f["next_funding_time"] if f else None
        rows.append({
            "symbol": sym,
            "spot_price_usdt": price,
            "futures_price_usdt": futu_last.get(sym),
            "funding_rate": rate,
            "next_funding_time_utc": ms_to_utc_iso(next_ts),
        })
    return rows

def save_csv(rows, path="binance_sorted_by_funding.csv"):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["symbol","spot_price_usdt","futures_price_usdt","funding_rate","next_funding_time_utc"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

def extract_base_asset(symbol):
    if symbol.endswith("USDT"):
        return symbol[:-4]
    return symbol

def get_top_funding_assets(top_n=20):
    spot_prices_by_symbol = get_all_spot_usdt_prices()
    futu_last_by_symbol = get_all_usdtm_last_prices()
    funding_by_symbol = get_all_usdtm_funding()
    rows = []
    for symbol, funding_info in funding_by_symbol.items():
        rate = funding_info["funding_rate"]
        if rate is None:
            continue
        spot_price = spot_prices_by_symbol.get(symbol)
        futu_price = futu_last_by_symbol.get(symbol)
        rows.append({
            "symbol": symbol,
            "asset": extract_base_asset(symbol),
            "spot_price_usdt": spot_price,
            "futures_price_usdt": futu_price,
            "funding_rate": rate,
            "next_funding_time_utc": ms_to_utc_iso(funding_info["next_funding_time"]),
        })
    rows.sort(key=lambda x: x["funding_rate"], reverse=True)
    return rows[:top_n]

if __name__ == "__main__":
    rows = build_table()

    # ✅ 过滤掉 funding_rate 为 None 的行
    rows = [r for r in rows if r["funding_rate"] is not None]

    print(f"len(rows): {len(rows)}")

    # ✅ 按 funding_rate 从高到低排序
    rows.sort(key=lambda x: x["funding_rate"], reverse=True)

    # 打印前 20 名（基于新函数）image.pngd
    print("\n📊 Funding Rate 排名前 20 的币种（仅含有永续合约）：")
    top_rows = get_top_funding_assets(20)
    for r in top_rows:
        spot_str = f"{r['spot_price_usdt']:.6f}" if r.get('spot_price_usdt') is not None else "NA"
        futu_str = f"{r['futures_price_usdt']:.6f}" if r.get('futures_price_usdt') is not None else "NA"
        print(f"{r['symbol']:12s} | Spot: {spot_str:>12s} | Futu: {futu_str:>12s} | Funding: {r['funding_rate']:.8f}")

    # 保存为 CSV（也只包含有资金费率的币）
    # save_csv(rows)
    # print(f"\n✅ 已保存至 binance_sorted_by_funding.csv （共 {len(rows)} 条）")

