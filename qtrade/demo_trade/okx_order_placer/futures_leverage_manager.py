#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Leverage Management Functions for OKX API
Handles getting and setting leverage for inverse perpetual contracts
"""
import os, time, json, hmac, base64, hashlib, requests
from typing import Optional, Dict, Any, List

from qtrade.demo_trade.order_placer import API_KEY, API_SECRET, API_PASSPHRASE

OKX_BASE_URL = "https://www.okx.com"
SIM_HEADER = {"x-simulated-trading": "1"}  # route to DEMO

def rfc3339():
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

def sign(timestamp: str, method: str, path: str, body: str, secret: str) -> str:
    data = f"{timestamp}{method.upper()}{path}{body}"
    digest = hmac.new(secret.encode(), data.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()

def auth_headers(ts: str, sig: str) -> Dict[str, str]:
    return {
        "OK-ACCESS-KEY": API_KEY,
        "OK-ACCESS-SIGN": sig,
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": API_PASSPHRASE,
        "Content-Type": "application/json",
        **SIM_HEADER,
    }

def okx_get(path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """GET request with authentication"""
    ts = rfc3339()
    query_string = ""
    if params:
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        path_with_query = f"{path}?{query_string}"
    else:
        path_with_query = path
    
    sig = sign(ts, "GET", path_with_query, "", API_SECRET)
    
    url = OKX_BASE_URL + path
    if query_string:
        url += f"?{query_string}"
    
    resp = requests.get(
        url,
        headers=auth_headers(ts, sig),
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") not in ("0", 0, None):
        raise RuntimeError(f"OKX error {data.get('code')}: {data.get('msg')} | data={data}")
    return data

def okx_post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """POST request with authentication"""
    ts = rfc3339()
    body = json.dumps(payload, separators=(",", ":"))
    sig = sign(ts, "POST", path, body, API_SECRET)
    resp = requests.post(
        OKX_BASE_URL + path,
        headers=auth_headers(ts, sig),
        data=body,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") not in ("0", 0, None):
        raise RuntimeError(f"OKX error {data.get('code')}: {data.get('msg')} | data={data}")
    return data

def get_account_leverage_info(instId: Optional[str] = None, mgnMode: str = "cross"):
    """
    获取账户杠杆信息
    Args:
        instId: 特定合约ID，如"BTC-USD-SWAP"，为None时获取所有
        mgnMode: 保证金模式，"cross"(全仓) 或 "isolated"(逐仓)
    Returns:
        dict: 杠杆信息
    """
    print(f"🔍 获取账户杠杆信息...")
    
    try:
        # 构建查询参数
        params = {"mgnMode": mgnMode}
        if instId:
            params["instId"] = instId
        
        data = okx_get("/api/v5/account/leverage-info", params)
        
        leverage_info = data.get("data", [])
        
        if not leverage_info:
            print("📭 没有找到杠杆信息")
            return []
        
        print(f"✅ 找到 {len(leverage_info)} 个杠杆配置:")
        
        for info in leverage_info:
            inst_id = info.get("instId")
            leverage = info.get("lever")
            mgn_mode = info.get("mgnMode")
            pos_side = info.get("posSide", "net")
            
            print(f"\n📊 杠杆详情:")
            print(f"  🔹 合约: {inst_id}")
            print(f"  📈 杠杆倍数: {leverage}x")
            print(f"  🎯 保证金模式: {mgn_mode}")
            print(f"  📏 仓位方向: {pos_side}")
        
        return leverage_info
        
    except Exception as e:
        print(f"❌ 获取杠杆信息时出错: {e}")
        return []

def get_current_leverage(instId: str, mgnMode: str = "cross") -> Optional[float]:
    """
    获取特定合约的当前杠杆倍数
    Args:
        instId: 合约ID，如"BTC-USD-SWAP"
        mgnMode: 保证金模式
    Returns:
        float: 杠杆倍数，如果未找到则返回None
    """
    leverage_info = get_account_leverage_info(instId=instId, mgnMode=mgnMode)
    
    for info in leverage_info:
        if info.get("instId") == instId:
            leverage = float(info.get("lever", 0))
            print(f"📊 {instId} 当前杠杆: {leverage}x")
            return leverage
    
    print(f"⚠️ 未找到 {instId} 的杠杆信息")
    return None

def set_leverage(instId: str, lever: int, mgnMode: str = "cross", posSide: Optional[str] = None):
    """
    设置杠杆倍数
    Args:
        instId: 合约ID，如"BTC-USD-SWAP"
        lever: 杠杆倍数
        mgnMode: 保证金模式，"cross"(全仓) 或 "isolated"(逐仓)
        posSide: 仓位方向，hedge模式下需要指定"long"或"short"
    Returns:
        dict: API响应结果
    """
    print(f"⚙️ 设置 {instId} 杠杆为 {lever}x...")
    
    try:
        payload = {
            "instId": instId,
            "lever": str(lever),
            "mgnMode": mgnMode
        }
        
        # 如果是hedge模式，需要指定仓位方向
        if posSide:
            payload["posSide"] = posSide
        
        result = okx_post("/api/v5/account/set-leverage", payload)
        
        if result.get("code") == "0":
            print(f"✅ 杠杆设置成功!")
            print(f"  🔹 合约: {instId}")
            print(f"  📈 杠杆: {lever}x")
            print(f"  🎯 模式: {mgnMode}")
            if posSide:
                print(f"  📏 方向: {posSide}")
            return result
        else:
            print(f"❌ 杠杆设置失败: {result}")
            return result
            
    except Exception as e:
        print(f"❌ 设置杠杆时出错: {e}")
        return {"error": str(e)}

def set_leverage_cross_inverse(ccy: str, lever: int = 1, posSide: Optional[str] = None):
    """
    为反向永续合约设置全仓杠杆
    Args:
        ccy: 保证金货币，BTC-USD-SWAP -> "BTC", ETH-USD-SWAP -> "ETH"
        lever: 杠杆倍数
        posSide: 仓位方向（hedge模式下需要）
    """
    print(f"⚙️ 设置 {ccy} 反向合约全仓杠杆为 {lever}x...")
    
    payload = {
        "mgnMode": "cross",
        "ccy": ccy.upper(),
        "lever": str(lever),
    }
    
    if posSide:
        payload["posSide"] = posSide
    
    try:
        result = okx_post("/api/v5/account/set-leverage", payload)
        
        if result.get("code") == "0":
            print(f"✅ {ccy} 反向合约杠杆设置成功: {lever}x")
            return result
        else:
            print(f"❌ {ccy} 反向合约杠杆设置失败: {result}")
            return result
            
    except Exception as e:
        print(f"❌ 设置 {ccy} 反向合约杠杆时出错: {e}")
        return {"error": str(e)}

def get_position_mode():
    """
    获取账户仓位模式（net模式 或 hedge模式）
    Returns:
        dict: 仓位模式信息
    """
    print(f"🔍 获取账户仓位模式...")
    
    try:
        data = okx_get("/api/v5/account/config")
        
        config_data = data.get("data", [])
        if config_data:
            config = config_data[0]
            pos_mode = config.get("posMode")
            auto_loan = config.get("autoLoan")
            
            print(f"📊 账户配置:")
            print(f"  🎯 仓位模式: {pos_mode} ({'双向持仓' if pos_mode == 'long_short_mode' else '单向持仓'})")
            print(f"  💰 自动借币: {auto_loan}")
            
            return config
        else:
            print(f"❌ 获取账户配置失败")
            return None
            
    except Exception as e:
        print(f"❌ 获取仓位模式时出错: {e}")
        return None

def demo_leverage_management():
    """演示杠杆管理功能"""
    print("🚀 杠杆管理演示...")
    print("=" * 50)
    
    # 1. 获取账户配置
    print("\n1️⃣ 获取账户配置")
    config = get_position_mode()
    
    # 2. 获取当前杠杆信息
    print("\n2️⃣ 获取当前杠杆信息")
    leverage_info = get_account_leverage_info()
    
    # 3. 获取BTC合约的杠杆
    print("\n3️⃣ 获取BTC-USD-SWAP杠杆")
    btc_leverage = get_current_leverage("BTC-USD-SWAP")
    
    # 4. 设置杠杆（演示，不实际执行）
    print("\n4️⃣ 杠杆设置示例（未实际执行）")
    print("  📝 设置BTC-USD-SWAP杠杆为5x:")
    print("     set_leverage('BTC-USD-SWAP', 5)")
    print("  📝 设置BTC全仓杠杆为3x:")
    print("     set_leverage_cross_inverse('BTC', 3)")
    
    return {
        "config": config,
        "leverage_info": leverage_info,
        "btc_leverage": btc_leverage
    }

# 快速访问函数
def btc_leverage():
    """获取BTC-USD-SWAP当前杠杆"""
    return get_current_leverage("BTC-USD-SWAP")

def eth_leverage():
    """获取ETH-USD-SWAP当前杠杆"""
    return get_current_leverage("ETH-USD-SWAP")

def set_btc_leverage(lever: int):
    """设置BTC-USD-SWAP杠杆"""
    return set_leverage("BTC-USD-SWAP", lever)

def set_eth_leverage(lever: int):
    """设置ETH-USD-SWAP杠杆"""
    return set_leverage("ETH-USD-SWAP", lever)

if __name__ == "__main__":
    # 运行演示
    demo_result = demo_leverage_management()
    
    print("\n✅ 杠杆管理功能演示完成!")
    print("📝 可用的主要函数:")
    print("  - get_current_leverage(instId)")
    print("  - set_leverage(instId, lever)")
    print("  - get_account_leverage_info()")
    print("  - get_position_mode()")
    print("  - btc_leverage(), eth_leverage()")
    print("  - set_btc_leverage(lever), set_eth_leverage(lever)")
