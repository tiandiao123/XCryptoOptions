#!/usr/bin/env python3
"""
OKX Current Options Data Module
获取期权实时价格、隐含波动率、Greeks等市场数据
"""

import requests
import json
from typing import Optional, Dict, List, Any
from datetime import datetime
import pandas as pd

OKX_BASE_URL = "https://www.okx.com"


def get_options_ticker(instId: Optional[str] = None, uly: Optional[str] = None) -> List[Dict]:
    """
    获取期权ticker数据（实时价格信息）
    
    Args:
        instId: 特定期权合约ID，如 "BTC-USD-241227-100000-C"
        uly: 标的指数，如 "BTC-USD"
    
    Returns:
        List[Dict]: 期权ticker数据
    """
    print(f"📊 获取期权ticker数据...")
    
    try:
        # 构建查询参数
        params = {"instType": "OPTION"}
        if instId:
            params["instId"] = instId
        if uly:
            params["uly"] = uly
        
        # 使用公开API
        url = f"{OKX_BASE_URL}/api/v5/market/tickers"
        if params:
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            url += f"?{query_string}"
        
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("code") != "0":
            print(f"❌ API错误: {data.get('msg')}")
            return []
        
        tickers = data.get("data", [])
        
        if instId:
            print(f"✅ 获取到 {instId} 的ticker数据")
        else:
            print(f"✅ 获取到 {len(tickers)} 个期权ticker数据")
        
        return tickers
        
    except Exception as e:
        print(f"❌ 获取期权ticker时出错: {e}")
        return []


def get_option_greeks(instId: Optional[str] = None, uly: Optional[str] = None) -> List[Dict]:
    """
    获取期权Greeks数据（Delta, Gamma, Theta, Vega等）
    
    Args:
        instId: 特定期权合约ID
        uly: 标的指数，如 "BTC-USD"
    
    Returns:
        List[Dict]: 期权Greeks数据
    """
    print(f"📈 获取期权Greeks数据...")
    
    try:
        # 构建查询参数
        params = {"instType": "OPTION"}
        if instId:
            params["instId"] = instId
        if uly:
            params["uly"] = uly
        
        # 使用公开API
        url = f"{OKX_BASE_URL}/api/v5/public/opt-summary"
        if params:
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            url += f"?{query_string}"
        
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("code") != "0":
            print(f"❌ API错误: {data.get('msg')}")
            return []
        
        greeks_data = data.get("data", [])
        
        if instId:
            print(f"✅ 获取到 {instId} 的Greeks数据")
        else:
            print(f"✅ 获取到 {len(greeks_data)} 个期权Greeks数据")
        
        return greeks_data
        
    except Exception as e:
        print(f"❌ 获取期权Greeks时出错: {e}")
        return []


def get_options_orderbook(instId: str, sz: int = 20) -> Dict[str, Any]:
    """
    获取期权订单簿数据
    
    Args:
        instId: 期权合约ID
        sz: 订单簿深度，默认20档
    
    Returns:
        Dict: 订单簿数据
    """
    print(f"📋 获取 {instId} 订单簿数据...")
    
    try:
        params = {"instId": instId, "sz": str(sz)}
        
        url = f"{OKX_BASE_URL}/api/v5/market/books"
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        url += f"?{query_string}"
        
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("code") != "0":
            print(f"❌ API错误: {data.get('msg')}")
            return {}
        
        orderbook_data = data.get("data", [])
        
        if orderbook_data:
            book = orderbook_data[0]
            
            bids = book.get("bids", [])
            asks = book.get("asks", [])
            
            print(f"✅ 获取到订单簿: {len(bids)} 买单, {len(asks)} 卖单")
            
            # 计算最佳买卖价
            best_bid = float(bids[0][0]) if bids else 0
            best_ask = float(asks[0][0]) if asks else 0
            spread = best_ask - best_bid if best_bid > 0 and best_ask > 0 else 0
            
            result = {
                "instId": instId,
                "bids": bids,
                "asks": asks,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread": spread,
                "mid_price": (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else 0,
                "timestamp": book.get("ts", "")
            }
            
            print(f"  💰 最佳买价: ${best_bid:.4f}")
            print(f"  💰 最佳卖价: ${best_ask:.4f}")
            print(f"  📊 价差: ${spread:.4f}")
            
            return result
        
        return {}
        
    except Exception as e:
        print(f"❌ 获取订单簿时出错: {e}")
        return {}


def get_atm_options_chain(underlying: str = "BTC-USD", 
                    expiry_date: Optional[str] = None, 
                    top_n: int = 20) -> Dict[str, Any]:
    """
    获取平值期权链数据（ATM附近的期权）
    
    Args:
        underlying: 标的资产
        expiry_date: 到期日期，如 "241227"
    
    Returns:
        Dict: ATM期权链数据
    """
    print(f"🎯 获取 {underlying} 平值期权链...")
    
    try:
        # 首先获取标的资产当前价格
        spot_price = get_underlying_price(underlying)
        if not spot_price:
            print(f"❌ 无法获取 {underlying} 当前价格")
            return {}
        
        print(f"📊 {underlying} 当前价格: ${spot_price:,.2f}")
        
        # 获取期权Greeks数据
        greeks_data = get_option_greeks(uly=underlying)
        
        if not greeks_data:
            return {}
        
        # 过滤特定到期日（如果指定）
        if expiry_date:
            greeks_data = [opt for opt in greeks_data if expiry_date in opt.get("instId", "")]
        
        # 按行权价分组，找到ATM附近的期权
        atm_options = []
        
        for option in greeks_data:
            inst_id = option.get("instId", "")
            
            # 解析行权价
            try:
                parts = inst_id.split("-")
                if len(parts) >= 5:
                    strike_price = float(parts[3])
                    option_type = parts[4]  # C or P
                    
                    # 计算与现价的距离
                    distance = abs(strike_price - spot_price)
                    moneyness = strike_price / spot_price
                    
                    option_info = {
                        "instId": inst_id,
                        "strike_price": strike_price,
                        "option_type": "Call" if option_type == "C" else "Put",
                        "distance_from_spot": distance,
                        "moneyness": moneyness,
                        "delta": float(option.get("delta", 0)),
                        "gamma": float(option.get("gamma", 0)),
                        "theta": float(option.get("theta", 0)),
                        "vega": float(option.get("vega", 0)),
                        "impliedVol": float(option.get("volLv", 0)),
                        "markPrice": float(option.get("markPx", 0))
                    }
                    
                    atm_options.append(option_info)
                    
            except Exception as e:
                continue
        
        # 按距离现价的远近排序
        atm_options.sort(key=lambda x: x["distance_from_spot"])
        
        # 取最接近的几个行权价
        atm_strikes = atm_options[:top_n]  # 取前20个最接近的
        
        # 按期权类型分组
        calls = [opt for opt in atm_strikes if opt["option_type"] == "Call"]
        puts = [opt for opt in atm_strikes if opt["option_type"] == "Put"]
        
        result = {
            "underlying": underlying,
            "spot_price": spot_price,
            "expiry_date": expiry_date,
            "atm_calls": calls,
            "atm_puts": puts,
            "total_options": len(atm_strikes)
        }
        
        print(f"✅ 找到 {len(calls)} 个看涨期权, {len(puts)} 个看跌期权")
        
        return result
        
    except Exception as e:
        print(f"❌ 获取ATM期权链时出错: {e}")
        return {}


def get_underlying_price(underlying: str) -> Optional[float]:
    """
    获取标的资产当前价格
    
    Args:
        underlying: 标的资产，如 "BTC-USD"
    
    Returns:
        float: 当前价格
    """
    try:
        # 构建对应的现货或永续合约ID
        if underlying == "BTC-USD":
            inst_id = "BTC-USD-SWAP"
        elif underlying == "ETH-USD":
            inst_id = "ETH-USD-SWAP"
        else:
            inst_id = f"{underlying}-SWAP"
        
        # 获取ticker数据
        url = f"{OKX_BASE_URL}/api/v5/market/ticker?instId={inst_id}"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("code") == "0" and data.get("data"):
            ticker = data["data"][0]
            last_price = float(ticker.get("last", 0))
            return last_price
        
        return None
        
    except Exception as e:
        print(f"⚠️ 获取 {underlying} 价格时出错: {e}")
        return None


def create_options_market_snapshot(underlying: str = "BTC-USD", limit_expiries: int = 2) -> Dict[str, Any]:
    """
    创建期权市场快照
    
    Args:
        underlying: 标的资产
        limit_expiries: 限制到期日数量
    
    Returns:
        Dict: 市场快照数据
    """
    print(f"📸 创建 {underlying} 期权市场快照...")
    
    # 获取标的价格
    spot_price = get_underlying_price(underlying)
    
    # 获取期权Greeks数据
    greeks_data = get_option_greeks(uly=underlying)
    
    # 获取期权ticker数据
    ticker_data = get_options_ticker(uly=underlying)
    
    # 按到期日分组
    expiry_groups = {}
    
    for option in greeks_data:
        inst_id = option.get("instId", "")
        
        try:
            parts = inst_id.split("-")
            if len(parts) >= 3:
                expiry = parts[2]
                
                if expiry not in expiry_groups:
                    expiry_groups[expiry] = {"calls": [], "puts": []}
                
                option_type = parts[4] if len(parts) >= 5 else ""
                
                if option_type == "C":
                    expiry_groups[expiry]["calls"].append(option)
                elif option_type == "P":
                    expiry_groups[expiry]["puts"].append(option)
                    
        except Exception:
            continue
    
    # 取最近的几个到期日
    sorted_expiries = sorted(expiry_groups.keys())[:limit_expiries]
    
    snapshot = {
        "underlying": underlying,
        "spot_price": spot_price,
        "timestamp": datetime.now().isoformat(),
        "expiries": {}
    }
    
    for expiry in sorted_expiries:
        calls = expiry_groups[expiry]["calls"]
        puts = expiry_groups[expiry]["puts"]
        
        # 计算统计信息
        call_ivs = [float(opt.get("volLv", 0)) for opt in calls if float(opt.get("volLv", 0)) > 0]
        put_ivs = [float(opt.get("volLv", 0)) for opt in puts if float(opt.get("volLv", 0)) > 0]
        
        snapshot["expiries"][expiry] = {
            "call_count": len(calls),
            "put_count": len(puts),
            "avg_call_iv": sum(call_ivs) / len(call_ivs) if call_ivs else 0,
            "avg_put_iv": sum(put_ivs) / len(put_ivs) if put_ivs else 0,
            "calls": calls[:10],  # 取前10个
            "puts": puts[:10]     # 取前10个
        }
        
        print(f"  📅 {expiry}: {len(calls)} 看涨, {len(puts)} 看跌")
    
    print(f"✅ 市场快照创建完成")
    
    return snapshot


def demo_current_options():
    """演示当前期权数据获取功能"""
    print("🚀 开始当前期权数据演示...\n")
    
    # 1. 获取BTC期权市场快照
    print("=" * 50)
    print("📸 Step 1: BTC期权市场快照")
    btc_snapshot = create_options_market_snapshot("BTC-USD", limit_expiries=2)

    
    # 2. 获取ATM期权链
    print("\n" + "=" * 50)
    print("🎯 Step 2: BTC ATM期权链")
    atm_chain = get_atm_options_chain("BTC-USD")
    
    # 3. 获取特定期权的订单簿（如果有ATM期权）
    if atm_chain and atm_chain.get("atm_calls"):
        print("\n" + "=" * 50)
        print("📋 Step 3: 特定期权订单簿")
        sample_option = atm_chain["atm_calls"][0]["instId"]
        orderbook = get_options_orderbook(sample_option)
    
    print("\n✅ 当前期权数据演示完成!")
    
    return {
        "btc_snapshot": btc_snapshot,
        "atm_chain": atm_chain
    }


if __name__ == "__main__":
    # 运行演示
    demo_result = demo_current_options()
    
    print("\n📝 可用的主要函数:")
    print("  - get_options_ticker(instId, uly)")
    print("  - get_option_greeks(instId, uly)")
    print("  - get_options_orderbook(instId, sz)")
    print("  - get_atm_options_chain(underlying, expiry_date)")
    print("  - get_underlying_price(underlying)")
    print("  - create_options_market_snapshot(underlying, limit_expiries)")
