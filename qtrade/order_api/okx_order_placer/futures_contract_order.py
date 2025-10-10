#!/usr/bin/env python3
import os, time, json, hmac, base64, hashlib, argparse, requests
from typing import Optional, Dict, Any

from qtrade.order_api.okx_order_placer.utils import get_current_btc_price, get_instrument_details

OKX_BASE_URL = "https://www.okx.com"  # demo vs live decided by header
SIM_HEADER = {"x-simulated-trading": "1"}  # route to DEMO


from qtrade.order_api.okx_order_placer import API_KEY, API_SECRET, API_PASSPHRASE


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

def okx_post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
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

def set_leverage_cross_inverse(ccy: str, lever: int = 1, posSide: Optional[str] = None):
    """
    Cross margin leverage for inverse perps uses the margin currency as `ccy`:
      BTC-USD-SWAP -> ccy="BTC"
      ETH-USD-SWAP -> ccy="ETH"
    """
    payload = {
        "mgnMode": "cross",
        "ccy": ccy.upper(),
        "lever": str(lever),
    }
    # If your account is in hedge mode, OKX may require posSide ("long"/"short") for isolated,
    # but for cross it's optional. We include only if provided.
    if posSide:
        payload["posSide"] = posSide
    return okx_post("/api/v5/account/set-leverage", payload)

def place_inverse_perp_order(
    instId: str,
    side: str,            # "buy" or "sell"
    sz_contracts: int,    # contracts (integer)
    ordType: str = "market",  # "market" or "limit"
    px: Optional[float] = None,
    posSide: Optional[str] = None,  # if hedge mode, use "long"/"short"
    tdMode: str = "cross",
    clOrdId: Optional[str] = None,
):
    payload = {
        "instId": instId,
        "tdMode": tdMode,
        "side": side.lower(),
        "ordType": ordType.lower(),
        "sz": str(int(sz_contracts)),
    }
    if px is not None and ordType.lower() == "limit":
        payload["px"] = str(px)
    if clOrdId:
        payload["clOrdId"] = clOrdId
    if posSide:
        payload["posSide"] = posSide  # required when hedge mode is enabled
    result = okx_post("/api/v5/trade/order", payload)

    if result.get("code") == "0":
        order_data = result.get("data", [])
        if order_data:
            order_id = order_data[0].get("ordId")
            print(f"✅ 订单提交成功!")
            print(f"  📝 订单ID: {order_id}")
            return order_id, result
        else:
            print(f"❌ 订单提交失败: 无订单数据")
            return None, result
    else:
        print(f"❌ 订单提交失败: {result}")
        return None, result


def place_inverse_perp_order_with_btc_notional(
    instId: str,
    side: str,
    btc_notional: float,
    ordType: str = "market",
    px: Optional[float] = None,
    posSide: Optional[str] = None,
    tdMode: str = "cross",
    clOrdId: Optional[str] = None,
):

    current_btc_price = get_current_btc_price("BTC-USD-SWAP")
    print(f"Current BTC SWAP price: {current_btc_price}")

    total_amount_in_usd = btc_notional * current_btc_price
    
    # get contract value from utils
    ct_val = get_instrument_details(instId=instId)["ctVal"]
    print(f"Contract value: {ct_val}")
    assert int(ct_val) == 100, "Contract value is not 100" 
    num_of_contracts = int(total_amount_in_usd / int(ct_val))


    return place_inverse_perp_order(
        instId=instId,
        side=side,
        sz_contracts=num_of_contracts,
        ordType=ordType,
        px=px,
        posSide=posSide,
        tdMode=tdMode,
        clOrdId=clOrdId,
    )

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

def get_current_positions(instType: str = "SWAP", instId: Optional[str] = None):
    """
    获取当前仓位信息
    Args:
        instType: 产品类型，默认为"SWAP"
        instId: 特定合约ID，如"BTC-USD-SWAP"，为None时获取所有仓位
    """
    print(f"🔍 获取当前仓位信息...")
    
    try:
        # 构建查询参数
        params = {"instType": instType}
        if instId:
            params["instId"] = instId
        
        data = okx_get("/api/v5/account/positions", params)
        
        positions = data.get("data", [])
        
        if not positions:
            print("📭 没有找到任何仓位")
            return []
        
        print(f"✅ 找到 {len(positions)} 个仓位:")
        
        active_positions = []
        for pos in positions:
            # 只显示有实际持仓的合约（pos不为0）
            position_size = float(pos.get("pos", 0))
            if position_size != 0:
                active_positions.append(pos)
                
                print(f"\n📊 仓位详情:")
                print(f"  🔹 合约: {pos.get('instId')}")
                print(f"  📏 仓位大小: {position_size} 张")
                print(f"  📈 方向: {'多头' if position_size > 0 else '空头'}")
                print(f"  💰 平均开仓价: ${float(pos.get('avgPx', 0)):,.1f}")
                print(f"  📊 标记价格: ${float(pos.get('markPx', 0)):,.1f}")
                print(f"  💵 未实现盈亏: {float(pos.get('upl', 0)):,.6f} {pos.get('ccy')}")
                print(f"  📈 盈亏率: {float(pos.get('uplRatio', 0)):.2%}")
                print(f"  🎯 杠杆: {pos.get('lever')}x")
                print(f"  📏 Position Size: {float(pos.get('pos', 0))} 张")
        
        return active_positions
        
    except Exception as e:
        print(f"❌ 获取仓位时出错: {e}")
        return []

def close_position(instId: str, pos_side: Optional[str] = None):
    """
    平仓指定合约的仓位
    Args:
        instId: 合约ID，如"BTC-USD-SWAP"
        pos_side: 仓位方向，net模式下为None，hedge模式下为"long"或"short"
    """
    print(f"🔄 准备平仓 {instId}...")
    
    # 首先获取当前仓位信息
    positions = get_current_positions(instId=instId)
    
    if not positions:
        print(f"❌ 没有找到 {instId} 的活跃仓位")
        return None
    
    for pos in positions:
        if pos.get("instId") == instId:
            position_size = float(pos.get("pos", 0))
            
            if position_size == 0:
                print(f"⚠️  {instId} 仓位大小为0，无需平仓")
                continue
            
            # 确定平仓方向：多头仓位用sell平仓，空头仓位用buy平仓
            close_side = "sell" if position_size > 0 else "buy"
            close_size = abs(int(position_size))  # 平仓数量为仓位绝对值
            
            print(f"📤 执行平仓:")
            print(f"  🎯 合约: {instId}")
            print(f"  📏 仓位: {position_size} 张")
            print(f"  🔄 平仓方向: {close_side}")
            print(f"  📊 平仓数量: {close_size} 张")
            
            try:
                # 执行市价平仓单
                result = place_inverse_perp_order(
                    instId=instId,
                    side=close_side,
                    sz_contracts=close_size,
                    ordType="market",  # 市价单确保成交
                    posSide=pos_side,
                    tdMode="cross"
                )
                
                if result.get("code") == "0":
                    order_data = result.get("data", [])
                    if order_data:
                        order_id = order_data[0].get("ordId")
                        print(f"✅ 平仓订单提交成功!")
                        print(f"  📝 订单ID: {order_id}")
                        print(f"  💰 预期平仓: {close_size} 张 {instId}")
                        return order_id
                    else:
                        print(f"❌ 平仓订单提交失败: 无订单数据")
                else:
                    print(f"❌ 平仓失败: {result}")
                    
            except Exception as e:
                print(f"❌ 平仓时出错: {e}")
                
    return None

def close_all_positions():
    """
    平掉所有活跃仓位
    """
    print(f"🚨 准备平掉所有活跃仓位...")
    
    # 获取所有仓位
    positions = get_current_positions()
    
    if not positions:
        print(f"✅ 没有活跃仓位需要平仓")
        return []
    
    closed_orders = []
    
    for pos in positions:
        inst_id = pos.get("instId")
        position_size = float(pos.get("pos", 0))
        
        if position_size != 0:
            print(f"\n🎯 平仓 {inst_id}...")
            order_id = close_position(inst_id)
            if order_id:
                closed_orders.append({
                    "instId": inst_id,
                    "orderId": order_id,
                    "originalPosition": position_size
                })
    
    print(f"\n✅ 平仓操作完成，共提交 {len(closed_orders)} 个平仓订单")
    return closed_orders

def check_order_status(ord_id: str, inst_id: str):
    """
    检查订单状态
    """
    try:
        params = {
            "ordId": ord_id,
            "instId": inst_id
        }
        
        result = okx_get("/api/v5/trade/order", params)
        
        if result.get("data"):
            order_info = result["data"][0]
            status = order_info.get("state")
            filled_sz = order_info.get("fillSz", "0")
            
            print(f"📋 订单状态:")
            print(f"  🆔 订单ID: {ord_id}")
            print(f"  📊 状态: {status}")
            print(f"  ✅ 已成交: {filled_sz} 张")
            
            return order_info
        else:
            print(f"❌ 查询订单状态失败: {result}")
            return None
            
    except Exception as e:
        print(f"❌ 查询订单状态时出错: {e}")
        return None

def get_pending_orders(instType: str = "SWAP", instId: Optional[str] = None):
    """
    获取未成交订单
    Args:
        instType: 产品类型，默认为"SWAP"
        instId: 特定合约ID，如"BTC-USD-SWAP"，为None时获取所有订单
    """
    print(f"🔍 获取未成交订单...")
    
    try:
        # 构建查询参数
        params = {"instType": instType}
        if instId:
            params["instId"] = instId
        
        data = okx_get("/api/v5/trade/orders-pending", params)
        
        orders = data.get("data", [])
        
        if not orders:
            print("📭 没有找到未成交订单")
            return []
        
        print(f"✅ 找到 {len(orders)} 个未成交订单:")
        
        for order in orders:
            order_id = order.get("ordId")
            inst_id = order.get("instId")
            side = order.get("side")
            order_type = order.get("ordType")
            price = float(order.get("px", 0))
            size = float(order.get("sz", 0))
            filled_size = float(order.get("fillSz", 0))
            remaining_size = size - filled_size
            state = order.get("state")
            
            print(f"\n📋 订单详情:")
            print(f"  🆔 订单ID: {order_id}")
            print(f"  🔹 合约: {inst_id}")
            print(f"  📈 方向: {'买入' if side == 'buy' else '卖出'}")
            print(f"  🎯 类型: {order_type.upper()}")
            print(f"  💰 价格: ${price:,.1f}")
            print(f"  📊 数量: {size} 张")
            print(f"  ✅ 已成交: {filled_size} 张")
            print(f"  ⏳ 剩余: {remaining_size} 张")
            print(f"  📍 状态: {state}")
        
        return orders
        
    except Exception as e:
        print(f"❌ 获取订单时出错: {e}")
        return []

def cancel_order(ord_id: str, inst_id: str):
    """
    取消指定订单 - 支持限价单和市价单
    Args:
        ord_id: 订单ID
        inst_id: 合约ID
    Returns:
        bool: 取消是否成功
    """
    print(f"🚫 准备取消订单 {ord_id}...")
    
    try:
        payload = {
            "ordId": ord_id,
            "instId": inst_id
        }
        
        result = okx_post("/api/v5/trade/cancel-order", payload)
        
        if result.get("code") == "0":
            cancel_data = result.get("data", [])
            if cancel_data:
                cancel_info = cancel_data[0]
                cancel_result = cancel_info.get("sCode")
                cancel_msg = cancel_info.get("sMsg")
                
                if cancel_result == "0":
                    print(f"✅ 订单取消成功!")
                    print(f"  🆔 订单ID: {cancel_info.get('ordId')}")
                    print(f"  📊 结果: {cancel_msg}")
                    return True
                else:
                    print(f"⚠️ 订单取消失败: {cancel_result} - {cancel_msg}")
                    return False
            else:
                print(f"❌ 取消失败: 无返回数据")
                return False
        else:
            print(f"❌ 取消失败: {result}")
            return False
            
    except Exception as e:
        print(f"❌ 取消订单时出错: {e}")
        return False

def cancel_all_orders(instId: Optional[str] = None):
    """
    取消所有未成交订单
    Args:
        instId: 特定合约ID，为None时取消所有合约的订单
    Returns:
        list: 成功取消的订单列表
    """
    print(f"🚨 准备取消所有未成交订单...")
    
    # 获取所有未成交订单
    orders = get_pending_orders(instId=instId)
    
    if not orders:
        print(f"✅ 没有未成交订单需要取消")
        return []
    
    cancelled_orders = []
    
    for order in orders:
        order_id = order.get("ordId")
        inst_id = order.get("instId")
        order_type = order.get("ordType")
        
        print(f"\n🎯 取消订单 {order_id} ({inst_id}, {order_type.upper()})...")
        success = cancel_order(order_id, inst_id)
        if success:
            cancelled_orders.append({
                "orderId": order_id,
                "instId": inst_id,
                "orderType": order_type
            })
    
    print(f"\n✅ 取消操作完成，共取消 {len(cancelled_orders)} 个订单")
    return cancelled_orders

def place_and_track_order(
    instId: str,
    side: str,
    btc_notional: float,
    ordType: str = "limit",
    price_offset: float = -50.0,  # 价格偏移量（USD）
    posSide: Optional[str] = None,
    tdMode: str = "cross"
):
    """
    下单并跟踪订单号（特别适用于limit订单）
    Args:
        price_offset: 相对于当前价格的偏移量，负数表示低于市价
    Returns:
        dict: 包含订单信息的字典，包括orderId
    """
    print(f"🚀 下单并跟踪...")
    
    # 获取当前价格
    current_price = get_current_btc_price(instId)
    if not current_price:
        print("❌ 无法获取当前价格")
        return None
    
    # 计算订单价格
    if ordType.lower() == "limit":
        order_price = current_price + price_offset
        print(f"💰 当前价格: ${current_price:,.1f}")
        print(f"📊 订单价格: ${order_price:,.1f} (偏移: ${price_offset:+.1f})")
    else:
        order_price = None
        print(f"💰 市价单，当前价格: ${current_price:,.1f}")
    
    try:
        # 下单 - 这会返回 (order_id, result) 或 (None, result)
        order_id, order_result = place_inverse_perp_order_with_btc_notional(
            instId=instId,
            side=side,
            btc_notional=btc_notional,
            ordType=ordType,
            px=order_price,
            posSide=posSide,
            tdMode=tdMode
        )
        
        if order_id:
            print(f"✅ 订单提交成功!")
            print(f"  🆔 订单ID: {order_id}")
            print(f"  📊 合约: {instId}")
            print(f"  📈 方向: {side}")
            print(f"  💰 BTC名义: {btc_notional} BTC")
            print(f"  🎯 类型: {ordType.upper()}")
            
            # 返回订单信息
            return {
                "success": True,
                "orderId": order_id,
                "instId": instId,
                "side": side,
                "ordType": ordType,
                "price": order_price,
                "btc_notional": btc_notional,
                "result": order_result
            }
        else:
            print(f"❌ 订单提交失败")
            return {
                "success": False,
                "orderId": None,
                "error": order_result
            }
        
    except Exception as e:
        print(f"❌ 下单时出错: {e}")
        return {
            "success": False,
            "orderId": None,
            "error": str(e)
        }

def place_limit_order_relative_to_book(
    instId: str,
    side: str,
    btc_notional: float,
    offset_usd: float = 0,  # +/- USD from bid/ask
    posSide: Optional[str] = None
):
    """
    基于订单簿的bid-1/ask-1价格下限价单
    Args:
        instId: 合约ID
        side: "buy" 或 "sell"
        btc_notional: BTC名义金额
        offset_usd: 价格偏移，正数=高于bid/ask，负数=低于bid/ask
        posSide: 持仓方向
    Returns:
        dict: 订单信息，包含orderId
    """
    from qtrade.demo_trade.order_placer.orderbook import get_bid_ask
    
    print(f"📊 基于订单簿下{side}单...")
    
    # 获取当前订单簿
    book = get_bid_ask(instId)
    if not book:
        return {"success": False, "error": "Failed to get orderbook"}
    
    # 根据买卖方向确定限价
    if side.lower() == "buy":
        # 买单：基于bid-1价格
        limit_price = book["bid"] + offset_usd
        print(f"💰 当前Bid-1: ${book['bid']:,.1f}")
        print(f"🎯 买单限价: ${limit_price:,.1f} (偏移: ${offset_usd:+.1f})")
    else:
        # 卖单：基于ask-1价格  
        limit_price = book["ask"] + offset_usd
        print(f"💰 当前Ask-1: ${book['ask']:,.1f}")
        print(f"🎯 卖单限价: ${limit_price:,.1f} (偏移: ${offset_usd:+.1f})")
    
    # 下限价单
    order_id, result = place_inverse_perp_order_with_btc_notional(
        instId=instId,
        side=side,
        btc_notional=btc_notional,
        ordType="limit",
        px=limit_price,
        posSide=posSide
    )
    
    if order_id:
        return {
            "success": True,
            "orderId": order_id,
            "instId": instId,
            "side": side,
            "limit_price": limit_price,
            "reference_price": book["bid"] if side.lower() == "buy" else book["ask"],
            "offset": offset_usd,
            "btc_notional": btc_notional,
            "result": result
        }
    else:
        return {
            "success": False,
            "orderId": None,
            "error": result
        }

def demo_order_management():
    """演示完整的订单管理流程"""
    print("🚀 开始订单管理演示...")
    
    # 1. 查看当前未成交订单
    print("\n📊 Step 1: 查看当前未成交订单")
    orders = get_pending_orders()
    
    # 2. 下一个limit订单
    print("\n🎯 Step 2: 下limit订单")
    order_info = place_and_track_order(
        instId="BTC-USD-SWAP",
        side="buy",
        btc_notional=0.1,
        ordType="limit",
        price_offset=-100  # 低于市价100美元
    )
    
    # 3. 再次查看订单
    if order_info and order_info["success"]:
        print("\n📋 Step 3: 查看新订单")
        import time
        time.sleep(1)
        get_pending_orders(instId="BTC-USD-SWAP")
        
        # 4. 取消刚下的订单
        print("\n🚫 Step 4: 取消订单")
        cancel_order(order_info["orderId"], order_info["instId"])
        
        # 5. 验证订单已取消
        print("\n🔍 Step 5: 验证订单已取消")
        get_pending_orders(instId="BTC-USD-SWAP")
    
    return order_info

# write a function place limit order based on ask-1 and bid-1
