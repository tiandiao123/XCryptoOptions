#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 Inverse Perpetual Contract 异步下单功能
验证持仓模式和 P&L 追踪逻辑
"""

import time
from qtrade.optionstrader.master_trader.async_inverse_perp_placer import place_inverse_perp_async
from qtrade.order_api.okx.client.inverse_perp_client import OKXInversePerpClient
from qtrade.order_api.okx import API_KEY, API_SECRET, API_PASSPHRASE


def test_long_eth():
    """测试 Long ETH"""
    print("\n" + "="*70)
    print("🧪 测试 Long ETH-USD-SWAP")
    print("="*70)
    
    result = place_inverse_perp_async(
        inst_id="ETH-USD-SWAP",
        side="long",
        crypto_notional=0.1,  # 1 ETH
        simulated=True,       # 模拟盘
        wait_time=30.0,       # 等待30秒
        poll_interval=0.5     # 每0.5秒检查一次
    )
    
    print(f"\n✅ 执行结果:")
    print(f"   成功: {result.get('success')}")
    print(f"   订单ID: {result.get('order_id')}")
    print(f"   成交量: {result.get('filled_sz', 0):.0f} 张")
    print(f"   成交价: {result.get('avg_px', 0):.2f}")
    print(f"   执行方式: {result.get('execution_type')}")
    print(f"   总耗时: {result.get('total_time', 0):.2f}秒")
    
    return result


def test_short_eth():
    """测试 Short ETH"""
    print("\n" + "="*70)
    print("🧪 测试 Short ETH-USD-SWAP")
    print("="*70)
    
    result = place_inverse_perp_async(
        inst_id="ETH-USD-SWAP",
        side="short",
        crypto_notional=0.2,  # 1 ETH
        simulated=True,       # 模拟盘
        wait_time=60.0,       # 等待1分钟
        poll_interval=0.5
    )
    
    print(f"\n✅ 执行结果:")
    print(f"   成功: {result.get('success')}")
    print(f"   订单ID: {result.get('order_id')}")
    print(f"   成交量: {result.get('filled_sz', 0):.0f} 张")
    print(f"   成交价: {result.get('avg_px', 0):.2f}")
    print(f"   执行方式: {result.get('execution_type')}")
    print(f"   总耗时: {result.get('total_time', 0):.2f}秒")
    
    return result


def get_account_config(simulated=True):
    """查询账户配置（持仓模式）"""
    import requests
    from datetime import datetime, timezone
    import hmac
    import hashlib
    import base64
    import os
    
    print("\n" + "="*70)
    print("📋 查询账户配置")
    print("="*70)
    
    # 检查环境变量
    use_simulated = os.getenv("OKX_SIMULATED", "0") == "1" or simulated
    
    url = "https://www.okx.com/api/v5/account/config"
    method = "GET"
    path = "/api/v5/account/config"
    
    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    sign_str = f"{timestamp}{method}{path}"
    signature = base64.b64encode(
        hmac.new(API_SECRET.encode(), sign_str.encode(), hashlib.sha256).digest()
    ).decode()
    
    headers = {
        "OK-ACCESS-KEY": API_KEY,
        "OK-ACCESS-SIGN": signature,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": API_PASSPHRASE,
        "Content-Type": "application/json"
    }
    
    # 只在使用模拟盘时添加标志
    if use_simulated:
        headers["x-simulated-trading"] = "1"
    
    print(f"   环境: {'🧪 模拟盘' if use_simulated else '🔴 实盘'}")
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        
        if data.get("code") == "0" and data.get("data"):
            config = data["data"][0]
            pos_mode = config.get("posMode")
            
            print(f"\n✅ 账户配置:")
            print(f"   持仓模式: {pos_mode}")
            if pos_mode == "long_short_mode":
                print(f"   → 双向持仓模式（可同时持有多空，不会自动对冲）")
            elif pos_mode == "net_mode":
                print(f"   → 单向持仓模式（多空自动对冲）⚠️")
            
            print(f"   账户等级: {config.get('acctLv')}")
            print(f"   自动借币: {config.get('autoLoan')}")
            
            return pos_mode
        else:
            print(f"⚠️ 查询失败: {data}")
            print(f"   提示: 可能是 API Key 环境问题，继续测试...")
            return "unknown"
    except Exception as e:
        print(f"⚠️ 查询异常: {e}")
        print(f"   提示: 继续测试...")
        return "unknown"


def get_position_info(client, inst_id):
    """获取当前持仓信息"""
    pos = client.get_position(inst_id)
    
    if not pos:
        return {
            "has_position": False,
            "pos": 0,
            "pos_side": None,
            "avg_px": 0,
            "upl": 0
        }
    
    pos_value = float(pos.get("pos", 0) or 0)
    
    # 安全转换浮点数（处理空字符串）
    def safe_float(value, default=0):
        try:
            return float(value) if value else default
        except (ValueError, TypeError):
            return default
    
    return {
        "has_position": True,
        "pos": pos_value,
        "pos_side": "long" if pos_value > 0 else "short" if pos_value < 0 else "net",
        "avg_px": safe_float(pos.get("avgPx"), 0),
        "upl": safe_float(pos.get("upl"), 0),
        "upl_ratio": pos.get("uplRatio", "0"),
        "margin": safe_float(pos.get("margin"), 0)
    }


def get_order_fills_pnl(client, inst_id, order_id):
    """获取订单的详细成交和 P&L"""
    print(f"\n   🔍 查询订单成交详情...")
    
    try:
        # 方法1: 获取订单详情
        order_details = client.get_order_details(inst_id, order_id)
        
        if order_details:
            fill_pnl = float(order_details.get("fillPnl", 0) or 0)
            fee = float(order_details.get("fee", 0) or 0)
            fill_sz = float(order_details.get("accFillSz", 0) or 0)
            avg_px = float(order_details.get("avgPx", 0) or 0)
            
            print(f"   📊 订单详情:")
            print(f"      成交数量: {fill_sz:.0f} 张")
            print(f"      成交均价: {avg_px:.2f}")
            print(f"      Realized P&L: {fill_pnl:.6f} {'ETH' if 'ETH' in inst_id else 'BTC'}")
            print(f"      手续费: {abs(fee):.6f}")
            
            return {
                "fill_pnl": fill_pnl,
                "fee": fee,
                "fill_sz": fill_sz,
                "avg_px": avg_px
            }
    except Exception as e:
        print(f"   ⚠️ 查询订单详情失败: {e}")
    
    # 方法2: 获取 fills（更详细）
    try:
        fills_resp = client._request(
            "GET",
            "/api/v5/trade/fills",
            params={"instId": inst_id, "ordId": order_id},
            signed=True
        )
        
        if fills_resp.get("code") == "0":
            fills = fills_resp.get("data", [])
            
            if fills:
                print(f"\n   📋 成交明细 ({len(fills)} 笔):")
                
                total_pnl = 0
                total_fee = 0
                
                for i, fill in enumerate(fills, 1):
                    fill_pnl = float(fill.get("fillPnl", 0) or 0)
                    fee = float(fill.get("fee", 0) or 0)
                    fill_sz = float(fill.get("fillSz", 0) or 0)
                    fill_px = float(fill.get("fillPx", 0) or 0)
                    side = fill.get("side")
                    
                    total_pnl += fill_pnl
                    total_fee += abs(fee)
                    
                    if fill_pnl != 0:
                        print(f"      [{i}] {side} {fill_sz:.0f}张 @ {fill_px:.2f} → P&L: {fill_pnl:.6f} (平仓)")
                    else:
                        print(f"      [{i}] {side} {fill_sz:.0f}张 @ {fill_px:.2f} → P&L: 0 (开仓)")
                
                print(f"\n   💰 汇总:")
                print(f"      总 Realized P&L: {total_pnl:.6f}")
                print(f"      总手续费: {total_fee:.6f}")
                
                return {
                    "fill_pnl": total_pnl,
                    "fee": total_fee,
                    "fills_count": len(fills)
                }
    except Exception as e:
        print(f"   ⚠️ 查询 fills 失败: {e}")
    
    return {"fill_pnl": 0, "fee": 0}


def test_position_mode_and_pnl():
    """
    测试持仓模式和 P&L 追踪
    
    场景：
    1. Buy 0.1 ETH (开多仓)
    2. Sell 0.2 ETH (平多 + 开空)
    3. 验证 P&L 是否正确追踪
    """
    print("\n" + "🎯" * 35)
    print("测试: 持仓模式 & P&L 追踪")
    print("🎯" * 35)
    
    inst_id = "ETH-USD-SWAP"
    client = OKXInversePerpClient(
        api_key=API_KEY,
        api_secret=API_SECRET,
        passphrase=API_PASSPHRASE
    )
    
    # 步骤0: 查询账户配置
    pos_mode = get_account_config()
    
    # 步骤1: 清空现有持仓
    print("\n" + "="*70)
    print("🧹 步骤1: 清空现有持仓")
    print("="*70)
    
    initial_pos = get_position_info(client, inst_id)
    print(f"\n初始持仓: {initial_pos}")
    
    if initial_pos["has_position"]:
        print(f"\n⚠️ 检测到现有持仓，先平掉...")
        try:
            close_resp = client.close_position_market(inst_id)
            print(f"   平仓结果: {close_resp}")
            time.sleep(2)
        except Exception as e:
            print(f"   平仓失败: {e}")
    
    # 步骤2: Buy 0.1 ETH (开多仓)
    print("\n" + "="*70)
    print("📈 步骤2: Buy 0.1 ETH (开多仓)")
    print("="*70)
    
    result1 = place_inverse_perp_async(
        inst_id=inst_id,
        side="long",
        crypto_notional=0.1,
        simulated=True,
        wait_time=30.0
    )
    
    print(f"\n✅ 订单1结果: {result1.get('success')}")
    print(f"   订单ID: {result1.get('order_id')}")
    print(f"   成交: {result1.get('filled_sz', 0):.0f}张 @ {result1.get('avg_px', 0):.2f}")
    
    time.sleep(2)
    
    # 查询持仓
    pos_after_buy = get_position_info(client, inst_id)
    print(f"\n📊 买入后持仓:")
    print(f"   方向: {pos_after_buy['pos_side']}")
    print(f"   数量: {abs(pos_after_buy['pos']):.0f} 张")
    print(f"   均价: {pos_after_buy['avg_px']:.2f}")
    print(f"   未实现盈亏: {pos_after_buy['upl']:.6f} ETH")
    
    # 查询订单1的 P&L
    pnl1 = get_order_fills_pnl(client, inst_id, result1.get('order_id'))
    
    # 步骤3: Sell 0.2 ETH (应该先平多 0.1，再开空 0.1)
    print("\n" + "="*70)
    print("📉 步骤3: Sell 0.2 ETH (测试对冲逻辑)")
    print("="*70)
    print(f"\n💡 预期行为（如果是单向持仓模式）:")
    print(f"   1. 先平掉 {abs(pos_after_buy['pos']):.0f} 张多单 → 产生 Realized P&L")
    print(f"   2. 再开 ~30 张空单 → 不产生 P&L")
    
    result2 = place_inverse_perp_async(
        inst_id=inst_id,
        side="short",
        crypto_notional=0.2,
        simulated=True,
        wait_time=30.0
    )
    
    print(f"\n✅ 订单2结果: {result2.get('success')}")
    print(f"   订单ID: {result2.get('order_id')}")
    print(f"   成交: {result2.get('filled_sz', 0):.0f}张 @ {result2.get('avg_px', 0):.2f}")
    
    time.sleep(2)
    
    # 查询持仓
    pos_after_sell = get_position_info(client, inst_id)
    print(f"\n📊 卖出后持仓:")
    print(f"   方向: {pos_after_sell['pos_side']}")
    print(f"   数量: {abs(pos_after_sell['pos']):.0f} 张")
    print(f"   均价: {pos_after_sell['avg_px']:.2f}")
    print(f"   未实现盈亏: {pos_after_sell['upl']:.6f} ETH")
    
    # 🔍 重点：查询订单2的详细 P&L
    pnl2 = get_order_fills_pnl(client, inst_id, result2.get('order_id'))
    
    # 步骤4: 清理持仓
    print("\n" + "="*70)
    print("🧹 步骤4: 清理持仓")
    print("="*70)
    
    if pos_after_sell["has_position"]:
        try:
            close_resp = client.close_position_market(inst_id)
            print(f"   平仓结果: {close_resp.get('code')} - {close_resp.get('msg', 'OK')}")
        except Exception as e:
            print(f"   平仓失败: {e}")
    
    # 总结
    print("\n" + "="*70)
    print("📊 测试总结")
    print("="*70)
    
    print(f"\n🔹 持仓模式: {pos_mode}")
    
    print(f"\n🔹 订单1 (Buy 0.1 ETH):")
    print(f"   Realized P&L: {pnl1.get('fill_pnl', 0):.6f} ETH")
    print(f"   预期: 0 (纯开仓)")
    
    print(f"\n🔹 订单2 (Sell 0.2 ETH):")
    print(f"   Realized P&L: {pnl2.get('fill_pnl', 0):.6f} ETH")
    if pos_mode == "net_mode":
        print(f"   预期: 非零 (包含平仓的 P&L)")
    else:
        print(f"   预期: 0 (双向持仓不对冲)")
    
    print(f"\n💡 结论:")
    if pos_mode == "net_mode" and pnl2.get('fill_pnl', 0) != 0:
        print(f"   ✅ 单向持仓模式确认！Sell 订单包含了平仓 P&L")
        print(f"   ⚠️ 需要使用 fills API 来区分平仓和开仓部分")
    elif pos_mode == "long_short_mode":
        print(f"   ✅ 双向持仓模式，多空不会自动对冲")
    
    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    print("\n" + "🚀" * 35)
    print("Inverse Perp 异步下单测试")
    print("🚀" * 35 + "\n")
    
    # 主测试：持仓模式和 P&L 追踪
    test_position_mode_and_pnl()

