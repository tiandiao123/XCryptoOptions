#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试期权合约下单功能
验证修正后的BTC notional逻辑
"""

import sys
import os
sys.path.append('/home/ubuntu/options_trading')

from qtrade.order_api.deribit_order_placer.options_order import (
    place_options_market_order_btc_notional,
    find_atm_options,
    get_options_orderbook
)


def test_options_contract_logic():
    """测试期权合约逻辑"""
    print("🚀 测试期权合约下单逻辑")
    print("=" * 60)
    
    try:
        # 1. 找一个ATM期权进行测试
        print("📊 Step 1: 寻找ATM期权...")
        atm_options = find_atm_options("BTC", days_to_expiry=7, env="testnet")
        
        if atm_options.get("error"):
            print(f"❌ 无法找到ATM期权: {atm_options['error']}")
            return
        
        atm_calls = atm_options.get("atm_calls", [])
        if not atm_calls:
            print("❌ 没有找到ATM Call期权")
            return
        
        sample_instrument = atm_calls[0]["instrument_name"]
        print(f"✅ 找到测试期权: {sample_instrument}")
        
        # 2. 获取期权价格信息
        print(f"\n📋 Step 2: 获取期权市场数据...")
        orderbook = get_options_orderbook(sample_instrument, env="testnet")
        
        if orderbook:
            print(f"💰 当前市场:")
            print(f"   Best Bid: {orderbook.get('best_bid', 0):.4f}")
            print(f"   Best Ask: {orderbook.get('best_ask', 0):.4f}")
            print(f"   Spread: {orderbook.get('spread', 0):.4f}")
        
        # 3. 测试不同合约数量的计算
        print(f"\n🧮 Step 3: 测试合约数量计算...")
        
        test_cases = [
            {"contracts": 0.1, "desc": "0.1张合约 (0.1 BTC名义价值)"},
            {"contracts": 0.5, "desc": "0.5张合约 (0.5 BTC名义价值)"},
            {"contracts": 1.0, "desc": "1.0张合约 (1.0 BTC名义价值)"},
            {"contracts": 2.0, "desc": "2.0张合约 (2.0 BTC名义价值)"},
        ]
        
        for case in test_cases:
            print(f"\n📝 测试 {case['desc']}:")
            
            # 模拟下单（不实际执行）
            result = simulate_order_calculation(
                instrument=sample_instrument,
                side="buy",
                contracts=case["contracts"],
                env="testnet"
            )
            
            if result.get("success"):
                print(f"✅ 计算成功:")
                print(f"   合约数量: {result['contracts']}")
                print(f"   名义价值: {result['nominal_value']} {result['currency']}")
                print(f"   预估成本: {result['estimated_cost']:.4f} {result['currency']}")
                if result.get('spot_price', 0) > 0:
                    print(f"   现货价格: ${result['spot_price']:,.2f}")
            else:
                print(f"❌ 计算失败: {result.get('error')}")
        
        print(f"\n✅ 期权合约逻辑测试完成")
        print(f"💡 关键理解:")
        print(f"   - 每张BTC期权合约 = 1 BTC名义价值")
        print(f"   - 合约数量直接指定，不需要通过价格计算")
        print(f"   - 期权费 = 合约数量 × 期权价格")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


def simulate_order_calculation(instrument: str, side: str, contracts: float, env: str) -> dict:
    """
    模拟订单计算（不实际下单）
    """
    try:
        # 获取现货价格
        from qtrade.order_api.deribit_order_placer.futures_market_price import get_index_price
        
        if "BTC" in instrument.upper():
            spot_price = get_index_price("BTC", env)
            currency = "BTC"
        elif "ETH" in instrument.upper():
            spot_price = get_index_price("ETH", env)
            currency = "ETH"
        else:
            spot_price = 0
            currency = "Unknown"
        
        # 获取期权价格
        orderbook = get_options_orderbook(instrument, env=env)
        
        if not orderbook:
            return {"success": False, "error": "Failed to get orderbook"}
        
        best_bid = orderbook.get("best_bid", 0)
        best_ask = orderbook.get("best_ask", 0)
        
        if best_bid <= 0 or best_ask <= 0:
            return {"success": False, "error": "Invalid bid/ask prices"}
        
        mid_price = (best_bid + best_ask) / 2
        nominal_value = contracts * 1.0  # 每张合约 = 1单位名义价值
        estimated_cost = contracts * mid_price
        
        return {
            "success": True,
            "contracts": contracts,
            "nominal_value": nominal_value,
            "currency": currency,
            "spot_price": spot_price,
            "option_mid_price": mid_price,
            "estimated_cost": estimated_cost
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    test_options_contract_logic()
