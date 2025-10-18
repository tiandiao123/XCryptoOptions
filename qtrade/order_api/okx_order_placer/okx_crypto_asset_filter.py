import requests
from datetime import datetime, timezone
import csv

OKX_BASE = "https://www.okx.com"


def get_all_usdt_swap_instruments():
    # instType=SWAP returns perpetual contracts; filter for USDT margined (ctValCcy == 'USDT' or instId endswith '-USDT-SWAP')
    r = requests.get(f"{OKX_BASE}/api/v5/public/instruments", params={"instType": "SWAP"}, timeout=20)
    r.raise_for_status()
    data = r.json()
    instruments = data.get("data", [])
    return [it for it in instruments if it.get("instId", "").endswith("-USDT-SWAP")]


def get_funding_rates(inst_ids):
    # OKX funding rate endpoint supports single instId per request; batch over list
    funding = {}
    for inst_id in inst_ids:
        r = requests.get(f"{OKX_BASE}/api/v5/public/funding-rate", params={"instId": inst_id}, timeout=20)
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            continue
        it = data[0]
        rate = it.get("fundingRate")
        next_time = it.get("nextFundingTime")
        funding[inst_id] = {
            "funding_rate": float(rate) if rate is not None else None,
            "next_funding_time": int(next_time) if next_time is not None else None,
        }
    return funding


def ms_to_utc_iso(ms):
    if ms is None:
        return ""
    return datetime.fromtimestamp(ms/1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")


def get_spot_usdt_tickers():
    # OKX spot tickers
    r = requests.get(f"{OKX_BASE}/api/v5/market/tickers", params={"instType": "SPOT"}, timeout=20)
    r.raise_for_status()
    tickers = r.json().get("data", [])
    price_by_inst = {}
    for t in tickers:
        inst_id = t.get("instId")  # e.g., BTC-USDT
        last = t.get("last")
        if inst_id is None or last is None:
            continue
        if inst_id.endswith("-USDT"):
            price_by_inst[inst_id] = float(last)
    return price_by_inst


def get_swap_last_prices():
    # As fallback when spot price not available, use SWAP last price
    r = requests.get(f"{OKX_BASE}/api/v5/market/tickers", params={"instType": "SWAP"}, timeout=20)
    r.raise_for_status()
    tickers = r.json().get("data", [])
    price_by_inst = {}
    for t in tickers:
        inst_id = t.get("instId")  # e.g., BTC-USDT-SWAP
        last = t.get("last")
        if inst_id is None or last is None:
            continue
        price_by_inst[inst_id] = float(last)
    return price_by_inst


def build_table():
    instruments = get_all_usdt_swap_instruments()
    inst_ids = [it.get("instId") for it in instruments]
    funding = get_funding_rates(inst_ids)
    spot_prices = get_spot_usdt_tickers()
    swap_prices = get_swap_last_prices()

    rows = []
    for it in instruments:
        inst_id = it.get("instId")  # e.g., BTC-USDT-SWAP
        base = inst_id.split("-")[0] if inst_id else ""
        spot_inst = f"{base}-USDT"
        price = spot_prices.get(spot_inst)
        if price is None:
            # Fallback to the SWAP instrument last price if spot is unavailable
            price = swap_prices.get(inst_id)
        f = funding.get(inst_id)
        rate = f["funding_rate"] if f else None
        next_ts = f["next_funding_time"] if f else None
        rows.append({
            "inst_id": inst_id,
            "asset": base,
            "spot_price_usdt": price,
            "funding_rate": rate,
            "next_funding_time_utc": ms_to_utc_iso(next_ts),
        })
    return rows


def save_csv(rows, path="okx_sorted_by_funding.csv"):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["inst_id","asset","spot_price_usdt","funding_rate","next_funding_time_utc"])
        w.writeheader()
        for r in rows:
            w.writerow(r)


def get_top_funding_assets(top_n=20):
    rows = build_table()
    rows = [r for r in rows if r["funding_rate"] is not None and r["spot_price_usdt"] is not None]
    rows.sort(key=lambda x: x["funding_rate"], reverse=True)
    return rows[:top_n]


if __name__ == "__main__":
    rows = build_table()
    rows = [r for r in rows if r["funding_rate"] is not None]
    rows.sort(key=lambda x: x["funding_rate"], reverse=True)

    print("\n📊 OKX Funding Rate 排名前 20 的币种（USDT 永续）：")
    for r in rows[:20]:
        print(f"{r['inst_id']:16s} | {r['asset']:8s} | Price: {r['spot_price_usdt'] if r['spot_price_usdt'] is not None else 'NA':>12} | Funding: {r['funding_rate']:.6f}")

    # save_csv(rows)
    # print(f"\n✅ 已保存至 okx_sorted_by_funding.csv （共 {len(rows)} 条）")
