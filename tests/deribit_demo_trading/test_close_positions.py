#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试平掉所有期权持仓功能
验证 close_all_options_positions 函数
"""

import sys
import os
sys.path.append('/home/ubuntu/options_trading')

from qtrade.order_api.deribit_order_placer.options_order import (
    close_all_options_positions,
    get_options_positions,
    cancel_all_options_orders
)


def test_close_all_positions():
    """测试平掉所有持仓功能"""
    print("🚀 测试平掉所有期权持仓功能")
    print("=" * 60)
    
    try:
        # 1. 检查当前持仓
        print("📊 Step 1: 检查当前期权持仓...")
        print("-" * 40)
        
        btc_positions = get_options_positions("BTC", "testnet")
        eth_positions = get_options_positions("ETH", "testnet")
        
        total_positions = len(btc_positions) + len(eth_positions)
        
        print(f"📈 当前持仓统计:")
        print(f"   BTC期权持仓: {len(btc_positions)} 个")
        print(f"   ETH期权持仓: {len(eth_positions)} 个")
        print(f"   总持仓: {total_positions} 个")
        
        if total_positions == 0:
            print("📭 没有期权持仓，无法测试平仓功能")
            return
        
        # 显示持仓详情
        if btc_positions:
            print(f"\n🔍 BTC期权持仓详情:")
            for i, pos in enumerate(btc_positions, 1):
                print(f"   {i}. {pos.get('instrument_name', 'Unknown')}")
                print(f"      数量: {pos.get('size', 0)} 张")
                print(f"      方向: {pos.get('direction', 'Unknown')}")
                print(f"      标记价格: {pos.get('mark_price', 0):.4f}")
                print(f"      未实现盈亏: {pos.get('unrealized_pnl', 0):.8f}")
        
        # 2. 询问确认（在测试中自动确认）
        print(f"\n⚠️  即将平掉所有期权持仓...")
        print(f"💡 平仓方式: 反向市价单 + reduce_only=True")
        print(f"🔄 开始执行平仓操作...")
        
        # 3. 执行平仓
        print(f"\n📊 Step 2: 执行平仓操作...")
        print("-" * 40)
        
        result = close_all_options_positions(env="testnet")
        
        # 4. 分析结果
        print(f"\n📊 Step 3: 分析平仓结果...")
        print("-" * 40)
        
        if result.get("success"):
            closed_count = result.get("closed_count", 0)
            total_positions_processed = result.get("total_positions", 0)
            
            print(f"✅ 平仓操作成功完成!")
            print(f"   处理持仓总数: {total_positions_processed}")
            print(f"   成功平仓: {closed_count} 个")
            print(f"   失败: {result.get('failed_count', 0)} 个")
            
            # 显示成功平仓的详情
            closed_positions = result.get("closed_positions", [])
            if closed_positions:
                print(f"\n✅ 成功平仓详情:")
                for pos in closed_positions:
                    print(f"   - {pos['instrument']}")
                    print(f"     原持仓: {pos['original_direction']} {abs(pos['original_size'])} 张")
                    print(f"     平仓操作: {pos['close_side']} {pos['close_amount']} 张")
                    print(f"     订单ID: {pos['order_id']}")
            
            # 显示失败的详情
            failed_positions = result.get("failed_positions", [])
            if failed_positions:
                print(f"\n❌ 失败详情:")
                for pos in failed_positions:
                    print(f"   - {pos['instrument']}: {pos['error']}")
                    
        else:
            print(f"❌ 平仓操作失败: {result.get('error')}")
        
        # 5. 验证最终结果
        print(f"\n📊 Step 4: 验证最终结果...")
        print("-" * 40)
        
        btc_positions_after = get_options_positions("BTC", "testnet")
        eth_positions_after = get_options_positions("ETH", "testnet")
        
        total_positions_after = len(btc_positions_after) + len(eth_positions_after)
        
        print(f"📈 平仓后持仓统计:")
        print(f"   BTC期权持仓: {len(btc_positions_after)} 个")
        print(f"   ETH期权持仓: {len(eth_positions_after)} 个")
        print(f"   总持仓: {total_positions_after} 个")
        
        if total_positions_after == 0:
            print(f"🎉 所有期权持仓已成功平掉!")
        else:
            print(f"⚠️  仍有 {total_positions_after} 个持仓未平掉")
            
            if btc_positions_after:
                print(f"\n🔍 剩余BTC持仓:")
                for pos in btc_positions_after:
                    print(f"   - {pos.get('instrument_name', 'Unknown')}: "
                          f"{pos.get('direction', 'Unknown')} {pos.get('size', 0)} 张")
        
        print(f"\n✅ 平仓功能测试完成!")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


def test_close_specific_currency():
    """测试平掉特定币种的持仓"""
    print(f"\n🚀 测试平掉特定币种持仓")
    print("=" * 50)
    
    for currency in ["BTC", "ETH"]:
        print(f"\n🔍 测试平掉 {currency} 持仓...")
        
        # 检查当前持仓
        positions = get_options_positions(currency, "testnet")
        
        if positions:
            print(f"   发现 {len(positions)} 个 {currency} 持仓")
            # 注意：这里只是演示，不实际执行
            print(f"   💡 可以调用: close_all_options_positions(currency='{currency}', env='testnet')")
        else:
            print(f"   没有 {currency} 持仓")


def explain_close_vs_cancel():
    """解释平仓和取消的区别"""
    print(f"\n📚 平仓 vs 取消订单的区别:")
    print("=" * 40)
    print(f"🔒 平仓 (close_all_options_positions):")
    print(f"   - 平掉已有的期权持仓")
    print(f"   - 通过下反向市价单实现")
    print(f"   - 例如: 持有1张Call → 卖出1张Call")
    print(f"   - 使用 reduce_only=True 确保只减仓")
    print(f"")
    print(f"🚫 取消订单 (cancel_all_options_orders):")
    print(f"   - 取消未成交的挂单")
    print(f"   - 不影响已有持仓")
    print(f"   - 例如: 撤销挂出的限价单")


if __name__ == "__main__":
    test_close_all_positions()
    test_close_specific_currency()
    explain_close_vs_cancel()
