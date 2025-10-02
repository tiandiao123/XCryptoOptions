#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Market Order Placement (DEMO MODE)
Tests placing market orders for options contracts in demo trading environment
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qtrade.demo_trade.order_placer.options_order import (
    place_options_market_order,
    place_options_limit_order,
    get_options_positions,
    get_options_bid_ask
)

from qtrade.demo_trade.order_placer.options_contract import (
    get_atm_options_chain,
    get_option_greeks,
    get_underlying_price
)


def confirm_demo_mode():
    """确认当前是否为Demo模式"""
    print("🔍 确认交易模式...")
    print("✅ 当前使用: DEMO 模拟交易模式")
    print("   - 所有订单都是模拟的")
    print("   - 不会使用真实资金")
    print("   - 安全的测试环境")
    print("   - Header: {'x-simulated-trading': '1'}")
    return True


def find_valid_options_contract():
    """寻找有效的期权合约进行测试"""
    print("\n🔍 寻找有效的期权合约...")
    
    # 获取BTC当前价格
    btc_price = get_underlying_price("BTC-USD")
    if btc_price:
        print(f"📊 BTC当前价格: ${btc_price:,.2f}")
    
    # 获取ATM期权
    atm_options = get_atm_options_chain("BTC-USD")
    
    if not atm_options or not atm_options.get('atm_calls'):
        print("❌ 无法获取ATM期权数据")
        return None
    
    print(f"✅ 找到 {len(atm_options.get('atm_calls', []))} 个ATM看涨期权")
    
    # 测试前几个合约，找到有市场数据的
    valid_contracts = []
    
    for i, call_option in enumerate(atm_options['atm_calls'][:5]):
        contract_id = call_option['instId']
        
        print(f"\n📋 测试合约 {i+1}: {contract_id}")
        print(f"   行权价: ${call_option['strike_price']:,.0f}")
        print(f"   Delta: {call_option['delta']:.4f}")
        
        # 检查是否有市场数据
        bid_ask = get_options_bid_ask(contract_id)
        
        if bid_ask and bid_ask['bid'] > 0 and bid_ask['ask'] > 0:
            print(f"   ✅ 有市场数据:")
            print(f"      Bid: ${bid_ask['bid']:.4f}")
            print(f"      Ask: ${bid_ask['ask']:.4f}")
            print(f"      价差: {(bid_ask['spread']/bid_ask['mid_price']*100):.2f}%")
            
            valid_contracts.append({
                'contract_id': contract_id,
                'bid_ask': bid_ask,
                'option_info': call_option
            })
        else:
            print(f"   ❌ 无市场数据")
    
    if valid_contracts:
        print(f"\n✅ 找到 {len(valid_contracts)} 个有效合约")
        return valid_contracts[0]  # 返回第一个有效合约
    else:
        print(f"\n❌ 未找到有效的期权合约")
        return None


def test_market_order_buy(contract_info):
    """测试市场买单 (DEMO)"""
    print(f"\n📝 测试市场买单 (DEMO模式)")
    print("=" * 50)
    
    contract_id = contract_info['contract_id']
    bid_ask = contract_info['bid_ask']
    
    print(f"🎯 合约: {contract_id}")
    print(f"💰 当前市场:")
    print(f"   Bid: ${bid_ask['bid']:.4f}")
    print(f"   Ask: ${bid_ask['ask']:.4f}")
    print(f"   预期成交价: ${bid_ask['ask']:.4f} (买入时支付Ask价)")
    
    print(f"\n🚀 执行市场买单...")
    
    # 执行市场买单
    result = place_options_market_order(
        instId=contract_id,
        side="buy",
        sz=1
    )
    
    print(f"\n📊 订单结果:")
    if result['success']:
        print(f"✅ 订单成功!")
        print(f"   订单ID: {result['orderId']}")
        print(f"   合约: {result['instId']}")
        print(f"   方向: {result['side'].upper()}")
        print(f"   数量: {result['size']} 合约")
        print(f"   类型: {result['ordType'].upper()}")
        return result
    else:
        print(f"❌ 订单失败:")
        print(f"   错误: {result['error']}")
        return None


def test_market_order_sell(contract_info):
    """测试市场卖单 (DEMO)"""
    print(f"\n📝 测试市场卖单 (DEMO模式)")
    print("=" * 50)
    
    contract_id = contract_info['contract_id']
    bid_ask = contract_info['bid_ask']
    
    print(f"🎯 合约: {contract_id}")
    print(f"💰 当前市场:")
    print(f"   Bid: ${bid_ask['bid']:.4f}")
    print(f"   Ask: ${bid_ask['ask']:.4f}")
    print(f"   预期成交价: ${bid_ask['bid']:.4f} (卖出时收到Bid价)")
    
    print(f"\n🚀 执行市场卖单...")
    
    # 执行市场卖单
    result = place_options_market_order(
        instId=contract_id,
        side="sell",
        sz=1
    )
    
    print(f"\n📊 订单结果:")
    if result['success']:
        print(f"✅ 订单成功!")
        print(f"   订单ID: {result['orderId']}")
        print(f"   合约: {result['instId']}")
        print(f"   方向: {result['side'].upper()}")
        print(f"   数量: {result['size']} 合约")
        print(f"   类型: {result['ordType'].upper()}")
        return result
    else:
        print(f"❌ 订单失败:")
        print(f"   错误: {result['error']}")
        return None


def check_positions_after_orders():
    """检查下单后的持仓"""
    print(f"\n🔍 检查当前持仓...")
    print("=" * 50)
    
    positions = get_options_positions()
    
    if positions:
        print(f"✅ 找到 {len(positions)} 个持仓:")
        
        for i, pos in enumerate(positions):
            contract = pos.get('instId')
            size = float(pos.get('pos', 0))
            avg_price = float(pos.get('avgPx', 0))
            mark_price = float(pos.get('markPx', 0))
            pnl = float(pos.get('upl', 0))
            
            print(f"\n   📊 持仓 {i+1}: {contract}")
            print(f"      数量: {size} 合约 ({'多头' if size > 0 else '空头'})")
            print(f"      平均价: ${avg_price:.4f}")
            print(f"      标记价: ${mark_price:.4f}")
            print(f"      未实现盈亏: ${pnl:.4f}")
    else:
        print("📭 当前无持仓")
        print("💡 在DEMO模式下，订单可能不会立即显示持仓")
    
    return positions


def main():
    """主测试函数"""
    print("🚀 期权市场订单测试 (DEMO模式)")
    print("=" * 60)
    
    try:
        # 1. 确认Demo模式
        confirm_demo_mode()
        
        # 2. 寻找有效合约
        contract_info = find_valid_options_contract()
        
        if not contract_info:
            print("\n❌ 无法找到有效的期权合约进行测试")
            print("💡 可能原因:")
            print("   - 期权合约已过期")
            print("   - Demo环境限制")
            print("   - 市场数据不可用")
            return
        
        # 3. 测试市场买单
        buy_result = test_market_order_buy(contract_info)
        
        # 4. 测试市场卖单
        sell_result = test_market_order_sell(contract_info)
        
        # 5. 检查持仓
        positions = check_positions_after_orders()
        
        # 6. 总结
        print(f"\n" + "=" * 60)
        print(f"✅ 测试总结:")
        print(f"   📊 测试合约: {contract_info['contract_id']}")
        print(f"   🟢 买单结果: {'成功' if buy_result and buy_result.get('success') else '失败'}")
        print(f"   🔴 卖单结果: {'成功' if sell_result and sell_result.get('success') else '失败'}")
        print(f"   📋 当前持仓: {len(positions)} 个")
        
        if buy_result and buy_result.get('success'):
            print(f"   🆔 买单ID: {buy_result['orderId']}")
        
        if sell_result and sell_result.get('success'):
            print(f"   🆔 卖单ID: {sell_result['orderId']}")
        
        print(f"\n🎉 DEMO测试完成!")
        print(f"💡 所有订单都是模拟的，不涉及真实资金")
        
    except Exception as e:
        print(f"❌ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
