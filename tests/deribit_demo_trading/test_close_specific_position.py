#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试单个期权持仓平仓功能
"""
import sys
import os

# 添加项目根目录到 Python 路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, project_root)

from qtrade.order_api.deribit_order_placer.options_order import (
    close_specific_options_position,
    get_options_positions,
    place_options_market_order_btc_notional
)

def test_close_specific_position():
    """测试单个持仓平仓功能"""
    print("🚀 测试单个期权持仓平仓功能")
    print("=" * 60)
    
    # Step 1: 检查当前持仓
    print("📊 Step 1: 检查当前持仓...")
    btc_positions = get_options_positions("BTC", "testnet")
    eth_positions = get_options_positions("ETH", "testnet")
    all_positions = btc_positions + eth_positions
    
    print(f"💰 当前持仓状态:")
    print(f"   BTC期权持仓: {len(btc_positions)}")
    print(f"   ETH期权持仓: {len(eth_positions)}")
    print(f"   总持仓: {len(all_positions)}")


    
    if not all_positions:
        print("📭 没有持仓，先创建一个测试持仓...")
        
        # 创建一个小的测试持仓
        test_instrument = "BTC-10OCT25-122000-C"  # 选择一个深度虚值便宜期权
        print(f"🔄 创建测试持仓: {test_instrument}")
        
        create_result = place_options_market_order_btc_notional(
            instrument=test_instrument,
            side="buy",
            contracts=0.1,  # 小量测试
            env="testnet"
        )
        
        if create_result.get("success"):
            print("✅ 测试持仓创建成功")
            
            # 等待持仓生效
            import time
            time.sleep(30)
            
            # 重新获取持仓
            all_positions = get_options_positions("BTC", "testnet") + get_options_positions("ETH", "testnet")
        else:
            print(f"❌ 创建测试持仓失败: {create_result.get('error')}")
            return
    
    # 显示详细持仓信息
    if all_positions:
        print(f"\n📋 详细持仓信息:")
        for i, pos in enumerate(all_positions, 1):
            instrument = pos.get("instrument_name", "Unknown")
            size = pos.get("size", 0)
            direction = pos.get("direction", "unknown")
            mark_price = pos.get("mark_price", 0)
            unrealized_pnl = pos.get("unrealized_pnl", 0)
            
            print(f"   {i}. {instrument}")
            print(f"      Size: {size} ({direction})")
            print(f"      Mark Price: {mark_price:.4f}")
            print(f"      Unrealized PnL: {unrealized_pnl:.6f}")
            
            # 如果持仓不为0，测试平仓
            if abs(size) > 0.001:
                print(f"\n🔒 Step 2: 测试平掉持仓 {instrument}...")
                
                # 测试部分平仓（如果持仓大于0.1）
                if abs(size) > 0.1:
                    print(f"📊 测试部分平仓 (0.05张)...")
                    partial_result = close_specific_options_position(
                        instrument=instrument,
                        size=0.05,
                        env="testnet"
                    )
                    
                    if partial_result.get("success"):
                        print(f"✅ 部分平仓成功: {partial_result.get('message')}")
                    else:
                        print(f"❌ 部分平仓失败: {partial_result.get('error')}")
                
                # 测试全部平仓
                print(f"📊 测试全部平仓...")
                full_result = close_specific_options_position(
                    instrument=instrument,
                    env="testnet"
                )
                
                if full_result.get("success"):
                    print(f"✅ 全部平仓成功: {full_result.get('message')}")
                    print(f"   原始持仓: {full_result.get('original_size')} ({full_result.get('original_direction')})")
                    print(f"   平仓方向: {full_result.get('close_side')}")
                    print(f"   平仓数量: {full_result.get('close_amount')}")
                    print(f"   成交数量: {full_result.get('filled_amount')}")
                    print(f"   订单ID: {full_result.get('order_id')}")
                    
                    if 'new_size' in full_result:
                        print(f"   剩余持仓: {full_result.get('new_size')}")
                else:
                    print(f"❌ 全部平仓失败: {full_result.get('error')}")
                
                break  # 只测试第一个有效持仓
    
    # Step 3: 验证最终结果
    print(f"\n📊 Step 3: 验证最终持仓状态...")
    final_positions = get_options_positions("BTC", "testnet") + get_options_positions("ETH", "testnet")
    
    print(f"💰 最终持仓状态:")
    print(f"   总持仓数: {len(final_positions)}")
    
    for pos in final_positions:
        instrument = pos.get("instrument_name")
        size = pos.get("size", 0)
        if abs(size) > 0.001:
            print(f"   - {instrument}: {size} 张")
    
    print(f"\n✅ 单个持仓平仓功能测试完成")

def test_close_nonexistent_position():
    """测试平掉不存在的持仓"""
    print(f"\n🔍 测试平掉不存在的持仓...")
    
    fake_instrument = "BTC-31DEC99-999999-C"
    result = close_specific_options_position(
        instrument=fake_instrument,
        env="testnet"
    )
    
    if not result.get("success"):
        print(f"✅ 正确处理不存在的持仓: {result.get('error')}")
    else:
        print(f"❌ 意外成功处理不存在的持仓")

if __name__ == "__main__":
    test_close_specific_position()
    test_close_nonexistent_position()
    
    print(f"\n🎉 所有测试完成!")
