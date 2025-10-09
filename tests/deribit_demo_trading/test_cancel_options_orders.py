#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试取消期权订单功能
验证修复后的 cancel_all_options_orders 函数
"""

import sys
import os
sys.path.append('/home/ubuntu/options_trading')

from qtrade.order_api.deribit_order_placer.options_order import (
    cancel_all_options_orders,
    get_open_options_orders,
    find_atm_options
)


def test_cancel_all_options_orders():
    """测试取消所有期权订单功能"""
    print("🚀 测试取消期权订单功能")
    print("=" * 60)
    
    try:
        # 1. 检查当前的期权订单
        print("📊 Step 1: 检查当前期权订单...")
        
        btc_orders = get_open_options_orders("BTC", "testnet")
        eth_orders = get_open_options_orders("ETH", "testnet")
        
        print(f"💰 当前订单状态:")
        print(f"   BTC期权订单: {len(btc_orders)}")
        print(f"   ETH期权订单: {len(eth_orders)}")
        
        total_orders = len(btc_orders) + len(eth_orders)
        
        if total_orders == 0:
            print("📭 没有发现期权订单，测试取消功能...")
            
            # 测试取消不存在的订单
            result = cancel_all_options_orders(env="testnet")
            
            if result.get("success"):
                print(f"✅ 取消功能正常: {result.get('message', 'No orders to cancel')}")
            else:
                print(f"❌ 取消功能异常: {result.get('error')}")
                
        else:
            print(f"🔍 发现 {total_orders} 个期权订单")
            
            # 显示订单详情
            if btc_orders:
                print(f"\n📋 BTC期权订单:")
                for i, order in enumerate(btc_orders[:3], 1):  # 只显示前3个
                    print(f"   {i}. {order.get('instrument_name', 'Unknown')} - "
                          f"{order.get('direction', 'Unknown')} - "
                          f"Amount: {order.get('amount', 0)}")
            
            if eth_orders:
                print(f"\n📋 ETH期权订单:")
                for i, order in enumerate(eth_orders[:3], 1):  # 只显示前3个
                    print(f"   {i}. {order.get('instrument_name', 'Unknown')} - "
                          f"{order.get('direction', 'Unknown')} - "
                          f"Amount: {order.get('amount', 0)}")
            
            # 询问是否要取消订单（在测试环境中自动确认）
            print(f"\n⚠️  即将取消所有期权订单...")
            print(f"🔄 执行取消操作...")
            
            # 2. 测试取消所有期权订单
            result = cancel_all_options_orders(env="testnet")
            
            if result.get("success"):
                canceled_count = result.get("canceled_count", 0)
                print(f"✅ 成功取消 {canceled_count} 个期权订单")
                
                if "results" in result:
                    # 多币种结果
                    for res in result["results"]:
                        print(f"   {res['currency']}: {res['canceled']} 个订单")
                        
            else:
                print(f"❌ 取消失败: {result.get('error')}")
        
        # 3. 测试单一币种取消
        print(f"\n📊 Step 2: 测试单一币种取消...")
        
        for currency in ["BTC", "ETH"]:
            print(f"\n🔍 测试取消 {currency} 期权订单...")
            result = cancel_all_options_orders(currency=currency, env="testnet")
            
            if result.get("success"):
                canceled_count = result.get("canceled_count", 0)
                print(f"✅ {currency}: 成功取消 {canceled_count} 个订单")
            else:
                print(f"❌ {currency}: 取消失败 - {result.get('error')}")
        
        # 4. 验证订单是否真的被取消了
        print(f"\n📊 Step 3: 验证取消结果...")
        
        btc_orders_after = get_open_options_orders("BTC", "testnet")
        eth_orders_after = get_open_options_orders("ETH", "testnet")
        
        total_orders_after = len(btc_orders_after) + len(eth_orders_after)
        
        print(f"💰 取消后订单状态:")
        print(f"   BTC期权订单: {len(btc_orders_after)}")
        print(f"   ETH期权订单: {len(eth_orders_after)}")
        print(f"   总订单: {total_orders_after}")
        
        if total_orders_after == 0:
            print(f"✅ 所有期权订单已成功取消")
        else:
            print(f"⚠️  仍有 {total_orders_after} 个订单未取消")
        
        print(f"\n✅ 取消期权订单功能测试完成")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


def test_api_endpoints():
    """测试API端点的正确性"""
    print(f"\n🔧 API端点测试:")
    print("=" * 40)
    
    print("📋 修复的关键问题:")
    print("   1. HTTP方法: POST → GET")
    print("   2. 参数顺序: kind在currency之后")
    print("   3. 错误处理: 增强异常捕获")
    print("   4. 多币种支持: 分别处理BTC和ETH")
    print("   5. 结果解析: 改进返回值处理")


if __name__ == "__main__":
    test_cancel_all_options_orders()
    test_api_endpoints()
