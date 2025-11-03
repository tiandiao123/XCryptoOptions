import math
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from qtrade.optionstrader.arbitrage_searcher.option_data import OptionData


OKX_BASE = "https://www.okx.com"


def _okx_get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 15) -> Dict[str, Any]:
    url = f"{OKX_BASE}{path}"
    r = requests.get(url, params=params or {}, timeout=timeout)
    r.raise_for_status()
    data = r.json() or {}
    if data.get("code") not in ("0", 0, None):
        raise RuntimeError(f"OKX error {data.get('code')}: {data.get('msg')} | data={data}")
    return data


def _underlying_from_currency(currency: str) -> str:
    c = (currency or "").upper()
    if c == "BTC":
        return "BTC-USD"
    if c == "ETH":
        return "ETH-USD"
    # default passthrough if already OKX underlying
    return c


def get_okx_index_price(currency: str) -> float:
    """Fetch index price for underlying (e.g., BTC-USD)."""
    uly = _underlying_from_currency(currency)
    # Try index tickers first
    try:
        data = _okx_get("/api/v5/market/index-tickers", params={"instId": uly})
        arr = (data or {}).get("data", [])
        if arr:
            last = arr[0].get("idxPx") or arr[0].get("last")
            if last is not None:
                return float(last)
    except Exception:
        pass
    # Fallback to swap ticker if index not available
    try:
        swap = f"{uly.split('-')[0]}-USDT-SWAP"
        data = _okx_get("/api/v5/market/ticker", params={"instId": swap})
        arr = (data or {}).get("data", [])
        if arr:
            last = arr[0].get("last") or arr[0].get("markPx")
            if last is not None:
                return float(last)
    except Exception:
        pass
    raise ValueError(f"Failed to get index price for {currency}")


def list_okx_live_options(currency: str) -> List[Dict[str, Any]]:
    """List live option instruments for a given underlying currency (BTC/ETH)."""
    uly = _underlying_from_currency(currency)
    data = _okx_get("/api/v5/public/instruments", params={"instType": "OPTION", "uly": uly})
    arr = (data or {}).get("data", [])
    # Filter live tradable options
    result: List[Dict[str, Any]] = []
    for it in arr:
        if (it or {}).get("state") == "live":
            result.append(it)
    return result


def get_okx_option_market_data(inst_id: str, summary_cache: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Fetch bid/ask/mid, IV, greeks, open_interest for one option instrument.

    Strategy (robust):
    - ticker for bidPx/askPx/markPx (preferred for mid)
    - books as fallback for bid/ask
    - opt-summary for IV/greeks/OI (fall back to zeros if not available)
    """


    bid = ask = mid = 0.0

    # Preferred: ticker
    try:
        tk = _okx_get("/api/v5/market/ticker", params={"instId": inst_id})
        td = (tk or {}).get("data", [])
        if td:
            t0 = td[0]
            try:
                bid = float(t0.get("bidPx") or 0)
            except Exception:
                pass
            try:
                ask = float(t0.get("askPx") or 0)
            except Exception:
                pass
            try:
                mark_px = float(t0.get("markPx") or 0)
            except Exception:
                mark_px = 0.0
            if bid > 0 and ask > 0:
                mid = (bid + ask) / 2.0
            elif mark_px > 0:
                mid = mark_px
    except Exception:
        pass

    # Fallback to books if still missing bid/ask
    if bid <= 0 or ask <= 0 or mid <= 0:
        try:
            books = _okx_get("/api/v5/market/books", params={"instId": inst_id, "sz": "1"})
            bd = (books or {}).get("data", [])
            if bd:
                book = bd[0]
                bids = book.get("bids", [])
                asks = book.get("asks", [])
                if bids and bid <= 0:
                    bid = float(bids[0][0])
                if asks and ask <= 0:
                    ask = float(asks[0][0])
                if mid <= 0 and bid > 0 and ask > 0:
                    mid = (bid + ask) / 2.0
        except Exception:
            pass

    mark_iv = 0.0
    oi = 0
    greeks = {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0}

    # Use summary cache if provided; otherwise try fetching by uly
    if summary_cache and inst_id in summary_cache:
        s0 = summary_cache[inst_id]
        try:
            mv = s0.get("markVol") or s0.get("markVol24h") or 0
            mark_iv = float(mv) / 100.0 if float(mv) > 1 else float(mv)
        except Exception:
            mark_iv = 0.0
        try:
            oi = int(float(s0.get("openInterest", 0)))
        except Exception:
            oi = 0
        # Greeks mapping: support both plain and *BS suffix keys
        key_map = {
            "delta": ("delta", "deltaBS"),
            "gamma": ("gamma", "gammaBS"),
            "vega": ("vega", "vegaBS"),
            "theta": ("theta", "thetaBS"),
            "rho": ("rho", "rhoBS"),
        }
        for gk, aliases in key_map.items():
            for alias in aliases:
                try:
                    val = s0.get(alias)
                    if val is not None:
                        greeks[gk] = float(val)
                        break
                except Exception:
                    continue

    return {
        "best_bid": bid,
        "best_ask": ask,
        "mid_price": mid if mid > 0 else 0.0,
        "mark_iv": mark_iv,
        "open_interest": oi,
        "greeks": greeks,
    }


def get_okx_atm_options(config: Dict[str, Any], currency: str = "BTC") -> List[OptionData]:
    """Fetch ATM options for OKX and return as standardized OptionData list."""
    print(f"🔍 [OKX] 获取{currency} ATM期权数据...")

    # 1) Spot/index price
    spot = get_okx_index_price(currency)
    print(f"💰 {currency} 指数价格: ${spot:,.2f}")

    # 2) Live option instruments
    instruments = list_okx_live_options(currency)
    print(f"📊 找到{len(instruments)}个可交易期权")

    # 3) ATM tolerance
    atm_tol = float(config["strike_criteria"]["atm_tolerance_pct"])  # e.g., 0.02
    print(f"🚀 ATM筛选容忍度: ±{atm_tol:.1%}")

    # 4) Fetch opt-summary by underlying once and cache
    print(f"📡 [OKX] 批量获取 opt-summary...")
    uly = _underlying_from_currency(currency)
    summary_cache: Dict[str, Any] = {}
    try:
        summ_data = _okx_get("/api/v5/public/opt-summary", params={"uly": uly})
        sarr = (summ_data or {}).get("data", [])
        for s in sarr:
            iid = s.get("instId")
            if iid:
                summary_cache[iid] = s
        print(f"✅ 缓存了 {len(summary_cache)} 个合约的 IV/Greeks")
    except Exception as e:
        print(f"⚠️ 获取 opt-summary 失败: {e}")

    atm_options: List[OptionData] = []

    for inst in instruments:
        try:
            # OKX uses 'stk' for strike
            strike_val = inst.get("stk") or inst.get("strike") or 0
            strike = float(strike_val)
            if strike <= 0:
                continue

            # ATM filter
            deviation = abs(strike - spot) / spot
            if deviation > atm_tol:
                continue

            # Expiry and DTE
            exp_ms = int(inst.get("expTime", 0))
            if exp_ms <= 0:
                continue
            expiry_dt = datetime.fromtimestamp(exp_ms / 1000)
            dte = (expiry_dt - datetime.now()).days
            if dte <= 3:
                continue

            # Side/type mapping
            opt_type_okx = (inst.get("optType") or "").upper()  # C/P
            if opt_type_okx not in ("C", "P"):
                continue

            inst_id = inst.get("instId")
            if not inst_id:
                continue

            # Market data
            md = get_okx_option_market_data(inst_id, summary_cache=summary_cache)
            if not md:
                continue

            # Build OptionData
            option = OptionData(
                symbol=inst_id,
                strike=strike,
                expiry=expiry_dt.strftime("%Y-%m-%d"),
                days_to_expiry=dte,
                option_type=opt_type_okx,  # 'C' or 'P'
                iv=float(md.get("mark_iv", 0.0)),
                bid=float(md.get("best_bid", 0.0)),
                ask=float(md.get("best_ask", 0.0)),
                mid_price=float(md.get("mid_price", 0.0)),
                delta=float(md.get("greeks", {}).get("delta", 0.0)),
                net_delta=float(md.get("greeks", {}).get("delta", 0.0)),  # no net-delta from OKX; use delta as proxy
                gamma=float(md.get("greeks", {}).get("gamma", 0.0)),
                vega=float(md.get("greeks", {}).get("vega", 0.0)),
                theta=float(md.get("greeks", {}).get("theta", 0.0)),
                rho=float(md.get("greeks", {}).get("rho", 0.0)),
                open_interest=int(md.get("open_interest", 0)),
            )

            # Validation: accept if we have a meaningful mid (from bid/ask or markPx)
            if option.mid_price <= 0:
                continue

            atm_options.append(option)

        except Exception as e:
            print(f"⚠️ 处理期权{inst.get('instId', 'Unknown')}时出错: {e}")
            continue

    print(f"✅ [OKX] 筛选出{len(atm_options)}个有效ATM期权")
    return atm_options


if __name__ == "__main__":
    # Minimal manual test (adjust config path if needed)
    import yaml
    cfg_path = "/home/ubuntu/options_trading/qtrade/optionstrader/arbitrage_searcher/calendar_spread/calendar_spread.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    opts = get_okx_atm_options(cfg, currency="ETH")
    print(f"Got {len(opts)} options")



    for opt in opts:
        print("================================================")
        print(f"📌 {opt.symbol}")
        print(f"   执行价: ${opt.strike:,.2f}")
        print(f"   报价: Bid ${opt.bid:,.4f} / Ask ${opt.ask:,.4f} / Mid ${opt.mid_price:,.4f}")
        print(f"   波动率(IV): {opt.iv:.2%}")
        print(f"   持仓量(OI): {opt.open_interest}")
        print(f"   希腊字母: Δ {opt.delta:+.4f} | Γ {opt.gamma:+.4f} | ν {opt.vega:+.4f} | Θ {opt.theta:+.4f} | ρ {opt.rho:+.4f}")
        print(f"   到期: {opt.expiry} | 剩余: {opt.days_to_expiry} 天 | 类型: {opt.option_type}")
        print("================================================")

