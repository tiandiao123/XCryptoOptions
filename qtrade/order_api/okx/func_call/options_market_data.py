#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX Options Market Data Retrieval
获取期权市场数据（orderbook + Greeks）
"""

import time
from typing import Dict, Any, Optional
from qtrade.order_api.okx.client.options_client import OKXOptionsClient


def get_okx_option_market_data(inst_id: str, simulated: bool = True, max_retries: int = 3) -> Optional[Dict[str, Any]]:
    """
    获取OKX期权的完整市场数据（orderbook + Greeks）
    
    Args:
        inst_id: 期权合约ID (e.g., "ETH-USD-20260130-3400-C")
        simulated: 是否使用模拟盘
        max_retries: 最大重试次数（默认3次）
    
    Returns:
        {
            "bid": float,
            "ask": float,
            "mid_price": float,
            "mark_price": float,
            "mark_iv": float,
            "open_interest": int,
            "greeks": {
                "delta": float,
                "gamma": float,
                "vega": float,
                "theta": float
            }
        }
    """
    for attempt in range(max_retries):
        try:
            client = OKXOptionsClient(simulated=simulated)
            
            # 1. 获取Orderbook（带重试）
            orderbook = None
            for retry in range(max_retries):
                orderbook = client.get_orderbook(inst_id)
                if orderbook:
                    break
                if retry < max_retries - 1:
                    wait_time = 0.5 * (retry + 1)  # 递增等待: 0.5s, 1s, 1.5s
                    print(f"⚠️ 获取{inst_id}的orderbook失败，{wait_time}秒后重试... (尝试 {retry + 1}/{max_retries})")
                    time.sleep(wait_time)
            
            if not orderbook:
                print(f"❌ 重试{max_retries}次后仍无法获取{inst_id}的orderbook")
                if attempt < max_retries - 1:
                    continue
                return None
            
            # 2. 获取Option Summary（包含Greeks和IV，带重试）
            option_summary = None
            for retry in range(max_retries):
                option_summary = client.get_option_summary(inst_id)
                if option_summary:
                    break
                if retry < max_retries - 1:
                    wait_time = 0.5 * (retry + 1)
                    print(f"⚠️ 获取{inst_id}的option summary失败，{wait_time}秒后重试... (尝试 {retry + 1}/{max_retries})")
                    time.sleep(wait_time)
            
            if not option_summary:
                print(f"❌ 重试{max_retries}次后仍无法获取{inst_id}的option summary")
                if attempt < max_retries - 1:
                    continue
                return None
            
            # 提取Greeks
            greeks_raw = {
                "delta": option_summary["delta"],
                "gamma": option_summary["gamma"],
                "vega": option_summary["vega"],
                "theta": option_summary["theta"]
            }
            
            # 提取Mark Price和IV
            mark_price = option_summary["mark_price"]
            mark_iv = option_summary["mark_iv"]
            
            # 提取Open Interest
            open_interest = option_summary["open_interest"]
            
            return {
                "bid": orderbook["bid"],
                "ask": orderbook["ask"],
                "mid_price": orderbook["mid"],
                "mark_price": mark_price,
                "mark_iv": mark_iv,  # 已经是小数形式
                "open_interest": open_interest,
                "greeks": greeks_raw
            }
            
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 1.0 * (attempt + 1)
                print(f"❌ 获取{inst_id}市场数据失败: {e}")
                print(f"   {wait_time}秒后重试... (尝试 {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                continue
            else:
                print(f"❌ 获取{inst_id}市场数据失败（已重试{max_retries}次）: {e}")
                import traceback
                traceback.print_exc()
                return None
    
    return None


if __name__ == "__main__":
    # Test the function
    import sys
    
    # 测试Calendar Spread的两条腿
    test_symbols = [
        ("ETH-USD-251114-3400-C", "short", "sell"),   # 短期合约 (卖出)
        ("ETH-USD-260130-3400-C", "long", "buy"),     # 长期合约 (买入)
    ]
    
    print(f"\n{'='*70}")
    print(f"测试获取OKX期权市场数据")
    print(f"{'='*70}\n")
    
    print(f"🔧 环境: Live (read-only)")
    print(f"\n📊 测试Calendar Spread的Net Delta计算")
    print(f"策略: 卖出短期 (ETH-USD-251114-3400-C) + 买入长期 (ETH-USD-260130-3400-C)")
    print()
    
    greeks_data = []
    
    for test_symbol, leg_type, action in test_symbols:
        print(f"\n{'='*70}")
        print(f"📊 {leg_type.upper()} 腿: {test_symbol} ({action})")
        print(f"{'='*70}")
        
        data = get_okx_option_market_data(test_symbol, simulated=False)
        
        if data:
            # 获取option summary以显示PA vs BS对比
            from qtrade.order_api.okx.client.options_client import OKXOptionsClient
            client = OKXOptionsClient(simulated=False)
            summary = client.get_option_summary(test_symbol)
            
            print(f"\n✅ 成功获取市场数据:")
            print(f"   Bid: {data['bid']:.4f} ETH")
            print(f"   Ask: {data['ask']:.4f} ETH")
            print(f"   Mid: {data['mid_price']:.4f} ETH")
            print(f"   Mark Price: {data['mark_price']:.4f} ETH")
            print(f"   Mark IV: {data['mark_iv']:.2%}")
            print(f"   Open Interest: {data['open_interest']}")
            print(f"   Greeks:")
            print(f"      Delta (使用的值): {data['greeks']['delta']:.5f}")
            if summary:
                print(f"         ├─ deltaPA: {summary['delta_pa']:.5f} ← 币本位Delta")
                print(f"         └─ deltaBS: {summary['delta_bs']:.5f} ← BS理论Delta")
            print(f"      Gamma: {data['greeks']['gamma']:.5f}")
            print(f"      Vega: {data['greeks']['vega']:.5f}")
            print(f"      Theta: {data['greeks']['theta']:.5f}")
            
            # 计算持仓的Delta贡献
            delta_contribution = -data['greeks']['delta'] if action == "sell" else +data['greeks']['delta']
            print(f"\n   💰 持仓Delta贡献: {delta_contribution:+.5f}")
            
            greeks_data.append({
                "leg": leg_type,
                "action": action,
                "delta": data['greeks']['delta'],
                "delta_contribution": delta_contribution
            })
        else:
            print(f"\n❌ 获取市场数据失败")
            sys.exit(1)
    
    # 计算Calendar Spread的Net Delta
    if len(greeks_data) == 2:
        net_delta = sum(g["delta_contribution"] for g in greeks_data)
        print(f"\n{'='*70}")
        print(f"📊 Calendar Spread Net Delta 计算")
        print(f"{'='*70}")
        print(f"Short腿 (卖出): Delta = {greeks_data[0]['delta']:.5f}, 贡献 = {greeks_data[0]['delta_contribution']:+.5f}")
        print(f"Long腿  (买入): Delta = {greeks_data[1]['delta']:.5f}, 贡献 = {greeks_data[1]['delta_contribution']:+.5f}")
        print(f"\n🎯 Net Delta = {net_delta:+.5f}")
        print(f"   |Net Delta| = {abs(net_delta):.5f}")
        print()
        if abs(net_delta) > 0.05:
            print(f"⚠️  超过阈值 0.05，需要Delta对冲！")
        else:
            print(f"✅ 低于阈值 0.05，Delta风险可控")
    
    success_count = len(greeks_data)
    
    if success_count == 0:
        print(f"\n❌ 所有格式都失败了")
        sys.exit(1)
    
    sys.exit(0)

